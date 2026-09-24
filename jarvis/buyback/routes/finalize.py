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
    The NORMAL case: a record reaches here already BOUGHT with
    carpark_vehicle_id still NULL — Task 10's offer-decision route
    (offers.py::record_decision, via BuyBackService.record_decision)
    already transitions accept@FINAL_OFFER -> BOUGHT; the hand-off itself
    was deliberately left out of that transition (see
    buyback_service.py's record_decision docstring) and lives here instead.
    Defensively also accepts a record still sitting in FINAL_OFFER (e.g. a
    caller that hits this route before/without going through the decision
    route) by transitioning it to BOUGHT first. Any other status, or a
    BOUGHT record that already has a carpark_vehicle_id, is a 409.

  - POST /records/<id>/handoff/retry
    Retries ONLY the hand-off sub-step, for a BOUGHT record whose
    carpark_vehicle_id is still NULL because a prior finalize's hand-off
    failed (e.g. VehicleService.create_vehicle's duplicate-VIN guard).
    Does not re-stamp purchase_price_eur/bought_at/finalized_by — those
    were already set by the finalize call that got this far.

Both apply the SAME company-scoping/IDOR guard as records.py/offers.py
(_shared._guard_company), loaded via the SAME repo the record routes use
(_shared.records_repo.get_by_id), 404 before that guard runs.

The hand-off's own ValueError (invalid/duplicate VIN — see
carpark_handoff.py) is deliberately turned into a 200 (not a 409/500): the
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

from flask import jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback import lifecycle
from buyback.routes import _shared
from buyback.services.carpark_handoff import handoff_to_carpark
from core.roles.decorators import v2_permission_required


def _attempt_handoff(record_id, record):
    """Run handoff_to_carpark for `record` (already BOUGHT, carpark_vehicle_id
    still NULL) and translate the outcome into a Flask response.

    Success: stamps carpark_vehicle_id on the record, returns 200 with the
    fresh record.
    Failure (ValueError from the hand-off, e.g. duplicate VIN): the record is
    left exactly as it was (still BOUGHT, still NULL carpark_vehicle_id) so
    POST /handoff/retry can be called again later; the response is still
    `success: True` (the finalize/retry request itself succeeded) plus a
    `handoff_error` message.
    """
    try:
        vehicle = handoff_to_carpark(record, current_user.id)
    except ValueError as e:
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

    if record['status'] == lifecycle.BOUGHT:
        if record.get('carpark_vehicle_id') is not None:
            return jsonify({
                'success': False,
                'error': 'Record already handed off to CarPark',
            }), 409
    elif record['status'] == lifecycle.FINAL_OFFER:
        # Defensive path — the normal flow (Task 10's decision route) already
        # transitions accept@FINAL_OFFER -> BOUGHT before this route is ever
        # called, but tolerate being called directly on a still-FINAL_OFFER
        # record by doing that transition here first.
        try:
            record = _shared.service.transition(record, lifecycle.BOUGHT, current_user.id)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 409
    else:
        return jsonify({
            'success': False,
            'error': f"Cannot finalize a record in status {record['status']!r} "
                     f"(expected {lifecycle.FINAL_OFFER!r}, or {lifecycle.BOUGHT!r} "
                     f"with no CarPark vehicle yet)",
        }), 409

    # The accepted FINAL offer is the source of truth for the purchase price
    # — looked up server-side (never trusted from the request body).
    final_offer = _shared.offers_repo.latest_for_record(record_id)
    purchase_price = final_offer['amount_eur'] if final_offer else None

    record = _shared.records_repo.update(record_id, {
        'purchase_price_eur': purchase_price,
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
