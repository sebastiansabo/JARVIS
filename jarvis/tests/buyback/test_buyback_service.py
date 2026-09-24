"""Tests for BuyBackService (Task 8): guarded status transitions + offer
invariants (one-pending-per-record, latest-offer/status decision guards).

DB-backed (uses `require_real_db` from tests/buyback/conftest.py) — obtains
its connection via the repositories' own `database` layer, NOT raw
psycopg2.connect, mirroring tests/buyback/test_offer_repository.py and
tests/buyback/test_record_repository.py. Each test creates its own parent
buyback_records row via RecordRepository().create() with a unique
record_code + VIN, so reruns against the shared localhost/defaultdb never
collide with leftover rows from a previous run.

`notifier=None` throughout — Task 13's email module doesn't exist yet, and
per Ruling R2 BuyBackService must never import it at module top; these tests
exercise the no-notifier path only.
"""
import os

from buyback import lifecycle
from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.services.buyback_service import BuyBackService


def _code(prefix='BB-SVC'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    # Not checksum-valid (the schema doesn't enforce VIN format), just a
    # unique 17-char alnum string so concurrent/rerun tests never collide.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
        'seller_email': 'seller@example.com',
    }
    data.update(overrides)
    return RecordRepository().create(data)


def test_illegal_transition_raises(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    try:
        svc.transition(rec, lifecycle.BOUGHT, actor=1)
        assert False, 'expected ValueError'
    except ValueError:
        pass


def test_transition_updates_status_and_logs_event(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    updated = svc.transition(rec, lifecycle.CANCELLED, actor=1, details={'note': 'test'})
    assert updated['status'] == lifecycle.CANCELLED
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.CANCELLED


def test_post_initial_offer_advances_and_blocks_second_pending(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()

    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
    assert offer['id']
    assert offer['offer_type'] == 'initial'
    assert offer['client_decision'] == 'pending'

    rec2 = RecordRepository().get_by_id(rec['id'])
    assert rec2['status'] == lifecycle.INITIAL_OFFER

    try:
        svc.post_offer(rec2, 'initial', {'amount_eur': 1100, 'vat_status': 'no_vat'}, actor=1)
        assert False, 'expected ValueError (second pending offer of same round blocked)'
    except ValueError:
        pass


def test_post_offer_wrong_round_status_raises(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()  # PENDING_EVALUATION
    try:
        # 'final' round requires INSPECTION status
        svc.post_offer(rec, 'final', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
        assert False, 'expected ValueError'
    except ValueError:
        pass


def test_decision_accept_advances_to_inspection(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    rec2 = RecordRepository().get_by_id(rec['id'])
    updated = svc.record_decision(rec2, offer['id'], 'accepted', actor=2)

    assert updated['status'] == lifecycle.INSPECTION
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.INSPECTION


def test_decision_on_stale_offer_rejected(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    rec2 = RecordRepository().get_by_id(rec['id'])
    svc.record_decision(rec2, offer['id'], 'accepted', actor=2)  # now INSPECTION

    rec3 = RecordRepository().get_by_id(rec['id'])
    try:
        # deciding the same (now-decided, non-latest-pending) offer again must raise
        svc.record_decision(rec3, offer['id'], 'declined', actor=2)
        assert False, 'expected ValueError (stale/non-pending offer decision)'
    except ValueError:
        pass

    # record must not have moved from INSPECTION as a side effect of the rejected call
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.INSPECTION


def test_bad_decision_value_raises_and_leaves_offer_pending(require_real_db):
    # A bogus decision value must be rejected BEFORE any DB mutation, so the
    # offer stays 'pending' and remains actionable. This directly guards the
    # bug where record_decision wrote the offer first, then raised on the
    # unrecognized value — permanently stranding it non-'pending'.
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    rec2 = RecordRepository().get_by_id(rec['id'])
    try:
        svc.record_decision(rec2, offer['id'], 'maybe', actor=2)
        assert False, 'expected ValueError (unrecognized decision value)'
    except ValueError:
        pass

    # The offer must be untouched: still pending, no decider stamped.
    fresh_offer = OfferRepository().get(offer['id'])
    assert fresh_offer['client_decision'] == 'pending'
    assert fresh_offer['decided_by'] is None
    assert fresh_offer['decided_at'] is None
    # And the record must not have advanced off INITIAL_OFFER.
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.INITIAL_OFFER


def test_decision_with_no_offers_raises(require_real_db):
    # latest_for_record() is None (record has never had an offer) -> raise,
    # rather than dereferencing None.
    svc = BuyBackService(notifier=None)
    rec = RecordRepository().get_by_id(_record()['id'])
    try:
        svc.record_decision(rec, 123456789, 'accepted', actor=2)
        assert False, 'expected ValueError (no offer exists for record)'
    except ValueError:
        pass


def test_decision_on_superseded_offer_raises(require_real_db):
    # A newer pending offer exists; deciding the OLDER offer_id must hit the
    # `latest['id'] != offer_id` branch and raise. To get two offers on one
    # record without tripping one-pending-per-record via post_offer, the
    # first offer is decided (accepted -> INSPECTION), then a second (final)
    # offer is posted; the record is now FINAL_OFFER with the final offer as
    # latest+pending, but the first offer_id is stale.
    svc = BuyBackService(notifier=None)
    rec = _record()
    first = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    rec = RecordRepository().get_by_id(rec['id'])
    svc.record_decision(rec, first['id'], 'accepted', actor=2)  # -> INSPECTION

    rec = RecordRepository().get_by_id(rec['id'])
    second = svc.post_offer(rec, 'final', {'amount_eur': 900, 'vat_status': 'no_vat'}, actor=1)
    assert OfferRepository().latest_for_record(rec['id'])['id'] == second['id']

    rec = RecordRepository().get_by_id(rec['id'])  # FINAL_OFFER
    try:
        # deciding the older, superseded offer must raise (not the latest)
        svc.record_decision(rec, first['id'], 'accepted', actor=2)
        assert False, 'expected ValueError (superseded / non-latest offer)'
    except ValueError:
        pass

    # The still-latest final offer must remain untouched/pending.
    assert OfferRepository().get(second['id'])['client_decision'] == 'pending'
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.FINAL_OFFER


def test_decision_declined_initial_moves_to_lost_with_reason(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    rec2 = RecordRepository().get_by_id(rec['id'])
    updated = svc.record_decision(rec2, offer['id'], 'declined', actor=2, decline_reason='too low')

    assert updated['status'] == lifecycle.LOST
    fresh = RecordRepository().get_by_id(rec['id'])
    assert fresh['status'] == lifecycle.LOST
    assert fresh['lost_reason'] == 'too low'


def test_final_offer_accept_moves_to_bought(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()

    initial_offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
    rec = RecordRepository().get_by_id(rec['id'])
    svc.record_decision(rec, initial_offer['id'], 'accepted', actor=2)  # -> INSPECTION

    rec = RecordRepository().get_by_id(rec['id'])
    final_offer = svc.post_offer(rec, 'final', {'amount_eur': 900, 'vat_status': 'no_vat'}, actor=1)
    assert final_offer['offer_type'] == 'final'

    rec = RecordRepository().get_by_id(rec['id'])
    assert rec['status'] == lifecycle.FINAL_OFFER

    updated = svc.record_decision(rec, final_offer['id'], 'accepted', actor=2)
    assert updated['status'] == lifecycle.BOUGHT
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.BOUGHT


def test_final_offer_decline_moves_to_lost(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()

    initial_offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
    rec = RecordRepository().get_by_id(rec['id'])
    svc.record_decision(rec, initial_offer['id'], 'accepted', actor=2)  # -> INSPECTION

    rec = RecordRepository().get_by_id(rec['id'])
    final_offer = svc.post_offer(rec, 'final', {'amount_eur': 900, 'vat_status': 'no_vat'}, actor=1)

    rec = RecordRepository().get_by_id(rec['id'])
    updated = svc.record_decision(rec, final_offer['id'], 'declined', actor=2, decline_reason='client walked')

    assert updated['status'] == lifecycle.LOST
    fresh = RecordRepository().get_by_id(rec['id'])
    assert fresh['status'] == lifecycle.LOST
    assert fresh['lost_reason'] == 'client walked'


def test_notifier_called_on_post_offer_when_present(require_real_db):
    calls = {'email': [], 'sales': []}

    class FakeNotifier:
        def send_offer_email(self, record, offer):
            calls['email'].append((record['id'], offer['id'], record['status']))

        def notify_sales(self, record):
            calls['sales'].append((record['id'], record['status']))

    svc = BuyBackService(notifier=FakeNotifier())
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    # The notifier must see the FRESH post-transition status (INITIAL_OFFER),
    # not the stale PENDING_EVALUATION the record carried into post_offer.
    assert calls['email'] == [(rec['id'], offer['id'], lifecycle.INITIAL_OFFER)]
    assert calls['sales'] == [(rec['id'], lifecycle.INITIAL_OFFER)]


def test_no_notifier_does_not_raise(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    # must not raise despite notifier being None
    svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
