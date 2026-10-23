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
from buyback.repositories.event_repository import EventRepository
from buyback.services.buyback_service import BuyBackService
import buyback.services.notifications as nmod


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


def test_terminal_transition_stamps_closed_at(require_real_db):
    """CANCELLED/LOST must get a real closed_at so the UI's resolved-window
    (Active/Arhivă) logic has a resolution timestamp — set_status alone left it
    NULL."""
    svc = BuyBackService(notifier=None)
    rec = _record()
    assert rec['closed_at'] is None
    updated = svc.transition(rec, lifecycle.CANCELLED, actor=1)
    assert updated['closed_at'] is not None
    assert RecordRepository().get_by_id(rec['id'])['closed_at'] is not None


def test_reopen_clears_closed_at(require_real_db):
    """Reopening a LOST record (→ PENDING_EVALUATION) clears closed_at so it is
    treated as in-progress again."""
    svc = BuyBackService(notifier=None)
    rec = _record()
    svc.post_offer(rec, 'initial', {'amount_eur': 1000}, actor=1)
    rec = RecordRepository().get_by_id(rec['id'])
    offer = OfferRepository().latest_for_record(rec['id'])
    svc.record_decision(rec, offer['id'], 'declined', actor=1, decline_reason='x')
    lost = RecordRepository().get_by_id(rec['id'])
    assert lost['status'] == lifecycle.LOST
    assert lost['closed_at'] is not None
    reopened = svc.transition(lost, lifecycle.PENDING_EVALUATION, actor=1)
    assert reopened['closed_at'] is None


def test_transition_calls_notify_owner_with_event_and_status(require_real_db, monkeypatch):
    calls = []
    monkeypatch.setattr(nmod, 'notify_owner', lambda *a, **k: calls.append((a, k)))
    svc = BuyBackService(notifier=None)
    rec = _record(created_by=4242)
    svc.transition(rec, lifecycle.CANCELLED, actor=999)
    assert calls, 'transition must invoke notify_owner'
    args, kwargs = calls[0]
    assert args[1] == 'status_changed'          # event
    assert args[2] == 999                         # actor passed through
    assert kwargs.get('new_status') == lifecycle.CANCELLED


def test_post_second_initial_offer_supersedes_and_stays_initial(require_real_db):
    """The acquisition handler can issue as many offers as needed: re-posting
    an 'initial' offer while the record is already INITIAL_OFFER supersedes the
    still-pending offer (marks it 'superseded' — NOT 'declined', so no LOST
    transition) and replaces it, keeping the record in INITIAL_OFFER. Mirrors
    the sanctioned final-offer correction path, generalized to every round so a
    second offer is never blocked."""
    svc = BuyBackService(notifier=None)
    rec = _record()

    first = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
    assert first['id']
    assert first['offer_type'] == 'initial'
    assert first['client_decision'] == 'pending'

    rec2 = RecordRepository().get_by_id(rec['id'])
    assert rec2['status'] == lifecycle.INITIAL_OFFER

    second = svc.post_offer(rec2, 'initial', {'amount_eur': 1100, 'vat_status': 'no_vat'}, actor=1)

    # The first offer is superseded (not declined), the new one is the single
    # pending offer, and the record stays in INITIAL_OFFER (no transition).
    assert OfferRepository().get(first['id'])['client_decision'] == 'superseded'
    pending = OfferRepository().pending_for_record(rec['id'])
    assert pending is not None and pending['id'] == second['id']
    assert float(pending['amount_eur']) == 1100.0
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.INITIAL_OFFER


def test_post_initial_offer_supersedes_stuck_pending_in_pending_evaluation(require_real_db):
    """Recovery for a record left in PENDING_EVALUATION with an orphan pending
    offer (e.g. a force-status override moved the record back without touching
    its offers — the exact record-52 bug). Posting an initial offer supersedes
    the orphan and advances to INITIAL_OFFER instead of raising 'already has a
    pending offer'."""
    svc = BuyBackService(notifier=None)
    rec = _record()  # PENDING_EVALUATION

    # Orphan pending offer created directly (the "dumb" repo does not transition
    # the record), simulating the leftover state a force-status override leaves.
    orphan = OfferRepository().create(
        rec['id'], 'initial', 999, 'no_vat', None, None, created_by=1,
    )
    assert OfferRepository().pending_for_record(rec['id'])['id'] == orphan['id']

    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1200, 'vat_status': 'no_vat'}, actor=1)

    assert OfferRepository().get(orphan['id'])['client_decision'] == 'superseded'
    pending = OfferRepository().pending_for_record(rec['id'])
    assert pending is not None and pending['id'] == offer['id']
    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.INITIAL_OFFER


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


def _advance_to_final_offer(svc, amount):
    """Create a record and drive it to FINAL_OFFER with a pending final offer
    of `amount`. Returns (record_id, final_offer)."""
    rec = _record()
    svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)
    initial = OfferRepository().latest_for_record(rec['id'])
    svc.record_decision(RecordRepository().get_by_id(rec['id']), initial['id'], 'accepted', actor=2)  # -> INSPECTION
    final = svc.post_offer(
        RecordRepository().get_by_id(rec['id']), 'final',
        {'amount_eur': amount, 'vat_status': 'no_vat'}, actor=1,
    )  # -> FINAL_OFFER
    return rec['id'], final


def test_correct_final_offer_supersedes_pending_and_stays_final(require_real_db):
    """A posted final price can be CORRECTED: re-posting a 'final' offer while
    the record is already FINAL_OFFER supersedes the still-pending final offer
    (marks it 'superseded' — NOT 'declined', so no LOST transition) and
    replaces it with the new amount, keeping the record in FINAL_OFFER. This
    is the sanctioned way to amend an agreed final price that was previously
    impossible (the price appeared permanently locked once posted)."""
    svc = BuyBackService(notifier=None)
    rid, first_final = _advance_to_final_offer(svc, 10000)
    assert RecordRepository().get_by_id(rid)['status'] == lifecycle.FINAL_OFFER

    corrected = svc.post_offer(
        RecordRepository().get_by_id(rid), 'final',
        {'amount_eur': 9500, 'vat_status': 'no_vat'}, actor=7,
    )

    # Record stays FINAL_OFFER (no LOST, no illegal transition).
    assert RecordRepository().get_by_id(rid)['status'] == lifecycle.FINAL_OFFER
    # Old final offer superseded (not declined), new one is the single pending.
    assert OfferRepository().get(first_final['id'])['client_decision'] == 'superseded'
    pending = OfferRepository().pending_for_record(rid)
    assert pending is not None and pending['id'] == corrected['id']
    assert float(pending['amount_eur']) == 9500.0
    assert OfferRepository().latest_for_record(rid)['id'] == corrected['id']
    # A price-correction audit event is logged.
    actions = [e['action'] for e in EventRepository().list_for_record(rid)]
    assert 'offer_corrected' in actions


def test_correct_final_offer_then_accept_uses_corrected_price(require_real_db):
    """After correcting the final price, the seller decision flows normally:
    accepting the corrected (now-latest-pending) offer moves the record to
    BOUGHT carrying the corrected amount — the superseded offer never
    interferes with record_decision's latest-pending guard."""
    svc = BuyBackService(notifier=None)
    rid, _first = _advance_to_final_offer(svc, 10000)
    corrected = svc.post_offer(
        RecordRepository().get_by_id(rid), 'final',
        {'amount_eur': 9500, 'vat_status': 'no_vat'}, actor=7,
    )
    svc.record_decision(RecordRepository().get_by_id(rid), corrected['id'], 'accepted', actor=2)
    assert RecordRepository().get_by_id(rid)['status'] == lifecycle.BOUGHT
    accepted = OfferRepository().get(corrected['id'])
    assert accepted['client_decision'] == 'accepted'
    assert float(accepted['amount_eur']) == 9500.0


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


# ── Reopen from CANCELLED + force_status (admin override) ──────────────────

def test_reopen_from_cancelled_clears_closed_at(require_real_db):
    """CANCELLED is now reopenable (→ PENDING_EVALUATION) just like LOST; the
    transition must clear closed_at so the record returns to Active."""
    svc = BuyBackService(notifier=None)
    rec = _record()
    cancelled = svc.transition(rec, lifecycle.CANCELLED, actor=1)
    assert cancelled['status'] == lifecycle.CANCELLED
    assert cancelled['closed_at'] is not None
    reopened = svc.transition(cancelled, lifecycle.PENDING_EVALUATION, actor=1)
    assert reopened['status'] == lifecycle.PENDING_EVALUATION
    assert reopened['closed_at'] is None


def test_force_status_sets_arbitrary_status_and_logs_forced_event(require_real_db, monkeypatch):
    """force_status bypasses the state machine: CANCELLED -> FINAL_OFFER is an
    illegal lifecycle transition, but the admin override allows it, clears
    closed_at (active target), and logs a status_changed event flagged forced."""
    monkeypatch.setattr(nmod, 'notify_owner', lambda *a, **k: None)
    svc = BuyBackService(notifier=None)
    rec = _record()
    cancelled = svc.transition(rec, lifecycle.CANCELLED, actor=1)
    assert cancelled['closed_at'] is not None
    # Illegal via the normal path.
    assert not lifecycle.is_valid_transition(lifecycle.CANCELLED, lifecycle.FINAL_OFFER)

    forced = svc.force_status(cancelled, lifecycle.FINAL_OFFER, actor=7, note='manual fix')
    assert forced['status'] == lifecycle.FINAL_OFFER
    assert forced['closed_at'] is None

    events = EventRepository().list_for_record(rec['id'])
    status_events = [e for e in events if e['action'] == 'status_changed']
    forced_evt = status_events[0]  # newest first (ORDER BY created_at DESC)
    assert forced_evt['details']['forced'] is True
    assert forced_evt['details']['to'] == lifecycle.FINAL_OFFER
    assert forced_evt['details']['from'] == lifecycle.CANCELLED
    assert forced_evt['details']['note'] == 'manual fix'


def test_force_status_to_bought_stamps_bought_at_without_carpark(require_real_db, monkeypatch):
    """Forcing BOUGHT stamps bought_at (so Arhivă resolution time exists) but
    does NOT create/link a CarPark vehicle — that stays the finalize route."""
    monkeypatch.setattr(nmod, 'notify_owner', lambda *a, **k: None)
    svc = BuyBackService(notifier=None)
    rec = _record()
    assert rec['bought_at'] is None
    forced = svc.force_status(rec, lifecycle.BOUGHT, actor=1)
    assert forced['status'] == lifecycle.BOUGHT
    assert forced['bought_at'] is not None
    assert forced['closed_at'] is None
    assert forced.get('carpark_vehicle_id') is None


def test_force_status_rejects_unknown_status(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    try:
        svc.force_status(rec, 'NONSENSE', actor=1)
        assert False, 'expected ValueError for unknown status'
    except ValueError:
        pass


def test_force_status_rejects_noop(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()  # starts PENDING_EVALUATION
    try:
        svc.force_status(rec, lifecycle.PENDING_EVALUATION, actor=1)
        assert False, 'expected ValueError for no-op status change'
    except ValueError:
        pass


def test_force_status_notifies_owner(require_real_db, monkeypatch):
    calls = []
    monkeypatch.setattr(nmod, 'notify_owner', lambda *a, **k: calls.append((a, k)))
    svc = BuyBackService(notifier=None)
    rec = _record(created_by=555)
    svc.force_status(rec, lifecycle.LOST, actor=321)
    assert calls, 'force_status must invoke notify_owner'
    args, kwargs = calls[0]
    assert args[1] == 'status_changed'
    assert args[2] == 321
    assert kwargs.get('new_status') == lifecycle.LOST


# ── Consignment proposal (Propune consignație) ─────────────────────────────

_TERMS = {
    'commission_type': 'percent', 'commission_value': 12.0, 'currency': 'EUR',
    'owner_price': 15000.0, 'min_sale_price': 14000.0,
    'contract_number': 'CS-9', 'agreement_date': '2026-10-14', 'expiry_date': '2027-01-01',
}


def test_post_consignment_offer_advances_and_stores_terms(require_real_db):
    """A consignment proposal from PENDING_EVALUATION opens a 'consignment'
    offer (terms stored in JSONB, headline amount = owner_price) and moves the
    record to CONSIGNMENT_OFFER."""
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)

    assert offer['offer_type'] == 'consignment'
    assert offer['client_decision'] == 'pending'
    assert offer['consignment_terms'] == _TERMS
    assert float(offer['amount_eur']) == 15000.0  # headline = owner_price

    assert RecordRepository().get_by_id(rec['id'])['status'] == lifecycle.CONSIGNMENT_OFFER


def test_post_consignment_offer_without_owner_price_defaults_amount_zero(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    terms = {'commission_type': 'fixed', 'commission_value': 500.0, 'currency': 'EUR'}
    offer = svc.post_offer(rec, 'consignment', {'consignment_terms': terms}, actor=1)
    assert float(offer['amount_eur']) == 0


def test_post_consignment_offer_wrong_status_raises(require_real_db):
    """'consignment' requires PENDING_EVALUATION, like 'initial' — from
    INITIAL_OFFER it must raise."""
    svc = BuyBackService(notifier=None)
    rec = _record()
    svc.post_offer(rec, 'initial', {'amount_eur': 1000}, actor=1)  # -> INITIAL_OFFER
    rec2 = RecordRepository().get_by_id(rec['id'])
    try:
        svc.post_offer(rec2, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)
        assert False, 'expected ValueError (wrong pre-offer status for consignment)'
    except ValueError:
        pass


def test_consignment_decline_moves_to_lost(require_real_db):
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)
    rec2 = RecordRepository().get_by_id(rec['id'])
    updated = svc.record_decision(rec2, offer['id'], 'declined', actor=2, decline_reason='nu vrea')
    assert updated['status'] == lifecycle.LOST
    assert RecordRepository().get_by_id(rec['id'])['lost_reason'] == 'nu vrea'


def test_consignment_accept_hands_off_and_moves_to_consignat(require_real_db, monkeypatch):
    """Accepting a consignment proposal performs the CarPark custody hand-off
    (stubbed here), stamps the offer accepted, links the vehicle, and moves the
    record to CONSIGNAT. The hand-off receives the proposed terms re-coerced to
    typed values (Decimal/date) via validate_custody_agreement."""
    import buyback.services.carpark_handoff as handoff_mod
    calls = []
    monkeypatch.setattr(
        handoff_mod, 'handoff_to_carpark_custody',
        lambda record, agreement, actor: calls.append((record['id'], agreement, actor)) or {'id': 987654},
    )
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)
    rec2 = RecordRepository().get_by_id(rec['id'])
    updated = svc.record_decision(rec2, offer['id'], 'accepted', actor=7)

    assert updated['status'] == lifecycle.CONSIGNAT
    assert updated['carpark_vehicle_id'] == 987654
    fresh = RecordRepository().get_by_id(rec['id'])
    assert fresh['status'] == lifecycle.CONSIGNAT
    assert fresh['carpark_vehicle_id'] == 987654

    assert len(calls) == 1
    _rid, agreement, actor = calls[0]
    assert actor == 7
    assert agreement['commission_type'] == 'percent'
    assert float(agreement['commission_value']) == 12.0
    assert float(agreement['owner_price']) == 15000.0

    accepted = OfferRepository().get(offer['id'])
    assert accepted['client_decision'] == 'accepted'
    assert accepted['decided_by'] == 7


def test_consignment_accept_dup_vin_leaves_offer_pending(require_real_db, monkeypatch):
    """A dup/invalid VIN (ValueError from the hand-off) must leave the offer
    pending and the record in CONSIGNMENT_OFFER (retryable) — the decision is
    NOT stamped and no vehicle is linked."""
    import buyback.services.carpark_handoff as handoff_mod
    monkeypatch.setattr(
        handoff_mod, 'handoff_to_carpark_custody',
        lambda record, agreement, actor: (_ for _ in ()).throw(ValueError('duplicate VIN')),
    )
    svc = BuyBackService(notifier=None)
    rec = _record()
    offer = svc.post_offer(rec, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)
    rec2 = RecordRepository().get_by_id(rec['id'])
    try:
        svc.record_decision(rec2, offer['id'], 'accepted', actor=7)
        assert False, 'expected ValueError (dup VIN)'
    except ValueError:
        pass

    assert OfferRepository().get(offer['id'])['client_decision'] == 'pending'
    fresh = RecordRepository().get_by_id(rec['id'])
    assert fresh['status'] == lifecycle.CONSIGNMENT_OFFER
    assert fresh['carpark_vehicle_id'] is None


def test_notifier_not_called_for_consignment_offer(require_real_db):
    """The external seller-facing offer email (send_offer_email/notify_sales)
    is a buy-offer notification — it must NOT fire for a consignment proposal."""
    calls = {'email': [], 'sales': []}

    class FakeNotifier:
        def send_offer_email(self, record, offer):
            calls['email'].append(1)

        def notify_sales(self, record):
            calls['sales'].append(1)

    svc = BuyBackService(notifier=FakeNotifier())
    rec = _record()
    svc.post_offer(rec, 'consignment', {'consignment_terms': dict(_TERMS)}, actor=1)
    assert calls['email'] == []
    assert calls['sales'] == []
