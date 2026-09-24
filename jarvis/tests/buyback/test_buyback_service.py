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
            calls['email'].append((record['id'], offer['id']))

        def notify_sales(self, record):
            calls['sales'].append(record['id'])

    svc = BuyBackService(notifier=FakeNotifier())
    rec = _record()
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    assert calls['email'] == [(rec['id'], offer['id'])]
    assert calls['sales'] == [rec['id']]


def test_no_notifier_does_not_raise(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    # must not raise despite notifier being None
    svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
