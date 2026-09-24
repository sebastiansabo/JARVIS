"""Finalize routes — the CarPark hand-off on a BOUGHT buyback record:
stamps the purchase price/bought_at/finalized_by, then creates the actual
CarPark vehicle draft (photos carried over, back-linked) via
buyback.services.carpark_handoff.handoff_to_carpark. Offers a retry path for
when that hand-off sub-step fails on its own (e.g. duplicate VIN already in
CarPark).

Two endpoints, both gated by @v2_permission_required('buyback', 'record',
'finalize') (the Acquisition-role permission seeded by
migrations/domains/schema_roles.py::_seed_buyback_permissions_v2):

  - POST /records/<id>/finalize
    Operates ONLY on a record already moved to BOUGHT (with
    carpark_vehicle_id still NULL) by Task 10's offer-decision route
    (offers.py::record_decision, via BuyBackService.record_decision, which
    flips accept@FINAL_OFFER -> BOUGHT). That decision route is the ONLY
    path that verifies the seller actually accepted the final offer — the
    hand-off itself was deliberately left out of that transition (see
    buyback_service.py's record_decision docstring) and lives here instead.
    finalize does NOT transition a still-FINAL_OFFER record to BOUGHT
    itself: a bare state-graph transition wouldn't check acceptance, so the
    same Acquisition user who holds both offer.manage AND record.finalize
    could otherwise buy a car at a price the seller never agreed to. A
    still-FINAL_OFFER record is a 409 ("record the client decision first");
    any other non-BOUGHT status is a 409; a BOUGHT record that already has a
    carpark_vehicle_id is a 409 ("already handed off"). The purchase price
    is taken from the record's latest offer only after asserting it is a
    'final' offer with client_decision 'accepted'.

  - POST /records/<id>/handoff/retry
    Retries ONLY the hand-off sub-step, for a BOUGHT record whose
    carpark_vehicle_id is still NULL because a prior finalize's hand-off
    failed (e.g. VehicleService.create_vehicle's duplicate-VIN guard).
    Does not re-stamp purchase_price_eur/bought_at/finalized_by — those
    were already set by the finalize call that got this far.

Both apply the SAME company-scoping/IDOR guard as records.py/offers.py
(_shared._guard_company), loaded via the SAME repo the record routes use
(_shared.records_repo.get_by_id), 404 before that guard runs.

A hand-off failure (ANY exception — VehicleService's invalid/duplicate-VIN
ValueError, or a DB fault mid-create — see carpark_handoff.py and
_attempt_handoff) is deliberately turned into a 200 (not a 409/500): the
finalize/retry REQUEST itself succeeded (the record is correctly BOUGHT with
its purchase price stamped); only the CarPark-side vehicle creation failed,
which is a normal, retryable outcome that must never un-BOUGHT the record or
lose the purchase price. The response carries `handoff_error` so the caller
can surface a "retry hand-off" affordance.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos (RecordRepository, OfferRepository) and
buyback.services.carpark_handoff.handoff_to_carpark (which itself may use
carpark repos, but never inline SQL in this route file).
"""
from datetime import datetime, timezone

import logging

from flask import jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback import lifecycle
from buyback.routes import _shared
from buyback.services.carpark_handoff import handoff_to_carpark
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')


def _attempt_handoff(record_id, record):
    """Run handoff_to_carpark for `record` (already BOUGHT, carpark_vehicle_id
    still NULL) and translate the outcome into a Flask response.

    Success: stamps carpark_vehicle_id on the record, returns 200 with the
    fresh record.
    Failure (ANY exception from the hand-off, e.g. VehicleService's
    duplicate/invalid-VIN ValueError, or a DB fault mid-create): the record
    is left exactly as it was (still BOUGHT, still NULL carpark_vehicle_id)
    so POST /handoff/retry can be called again later; the response is still
    `success: True` (the finalize/retry request itself succeeded) plus a
    `handoff_error` message, 200.

    The catch is deliberately broad (`except Exception`, not just
    `ValueError`): the hand-off is a best-effort side step off an
    already-committed BOUGHT record — a non-ValueError fault (e.g. a DB error
    in VehicleService.create_vehicle's post-insert change_status) must never
    surface as a 500 that leaves the record BOUGHT-with-null-vehicle AND
    signals a hard error to the caller. (Accepted rare residual: if such a
    fault lands AFTER the carpark_vehicles INSERT but before we can stamp
    carpark_vehicle_id, a real orphan vehicle exists whose VIN would then
    block the dup-VIN guard on a later /handoff/retry — a rare mid-create DB
    fault, not solved here.)
    """
    try:
        vehicle = handoff_to_carpark(record, current_user.id)
    except Exception as e:
        logger.warning(
            'CarPark hand-off failed for buyback record %s — left BOUGHT with '
            'null carpark_vehicle_id, retryable', record_id, exc_info=True,
        )
        fresh = _shared.records_repo.get_by_id(record_id)
        return jsonify({
            'success': True,
            'record': _shared._serialize(fresh),
            'handoff_error': str(e),
        }), 200

    updated = _shared.records_repo.update(record_id, {'carpark_vehicle_id': vehicle['id']})
    return jsonify({'success': True, 'record': _shared._serialize(updated)}), 200


# ═══════════════════════════════════════════════
# FINALIZE
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/finalize', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'finalize')
def finalize_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    # finalize operates ONLY on a record already moved to BOUGHT by Task 10's
    # decision route (offers.py::record_decision -> BuyBackService.record_decision,
    # which flips accept@FINAL_OFFER -> BOUGHT and is the ONLY path that
    # verifies the seller actually accepted the final offer). A record still
    # sitting in FINAL_OFFER means the client's decision was never recorded —
    # finalize must NOT transition it to BOUGHT itself (a bare state-graph
    # transition wouldn't check acceptance, so the same Acquisition user who
    # holds both offer.manage AND record.finalize could buy a car at a price
    # the seller never agreed to). It's a 409 telling the caller to record the
    # decision first.
    if record['status'] != lifecycle.BOUGHT:
        if record['status'] == lifecycle.FINAL_OFFER:
            return jsonify({
                'success': False,
                'error': 'Record the client decision on the final offer first '
                         '(it must be accepted before finalizing)',
            }), 409
        return jsonify({
            'success': False,
            'error': f"Cannot finalize a record in status {record['status']!r} "
                     f"(only {lifecycle.BOUGHT!r} with no CarPark vehicle yet "
                     f"can be finalized)",
        }), 409

    if record.get('carpark_vehicle_id') is not None:
        return jsonify({
            'success': False,
            'error': 'Record already handed off to CarPark',
        }), 409

    # The accepted FINAL offer is the source of truth for the purchase price
    # — looked up server-side (never trusted from the request body). Because
    # the record is BOUGHT, its latest offer IS the accepted final offer; we
    # ASSERT that (offer_type 'final' + client_decision 'accepted') rather
    # than assume it, so the price can never come from a mislabeled/undecided
    # offer.
    final_offer = _shared.offers_repo.latest_for_record(record_id)
    if (
        final_offer is None
        or final_offer.get('offer_type') != 'final'
        or final_offer.get('client_decision') != 'accepted'
    ):
        return jsonify({
            'success': False,
            'error': 'No accepted final offer found for this record',
        }), 409

    record = _shared.records_repo.update(record_id, {
        'purchase_price_eur': final_offer['amount_eur'],
        'bought_at': datetime.now(timezone.utc),
        'finalized_by': current_user.id,
    })

    return _attempt_handoff(record_id, record)


# ═══════════════════════════════════════════════
# RETRY HAND-OFF
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/handoff/retry', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'finalize')
def retry_handoff(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.BOUGHT:
        return jsonify({
            'success': False,
            'error': f"Cannot retry hand-off on a record in status {record['status']!r} "
                     f"(only {lifecycle.BOUGHT!r} is retryable)",
        }), 409
    if record.get('carpark_vehicle_id') is not None:
        return jsonify({
            'success': False,
            'error': 'Record already handed off to CarPark',
        }), 409

    return _attempt_handoff(record_id, record)
