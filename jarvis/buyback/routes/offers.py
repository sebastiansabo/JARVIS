"""Offer routes — post an offer to a buyback record's seller, and record the
seller's decision on it.

Two endpoints:
  - POST /records/<id>/offers            gated by
    @v2_permission_required('buyback', 'offer', 'manage') — opens a new offer
    round (Acquisition-style role).
  - POST /records/<id>/offers/<oid>/decision  gated by
    @v2_permission_required('buyback', 'record', 'edit') — records the
    seller's accept/decline (Sales-style role).

Both apply the SAME company-scoping/IDOR guard as records.py
(_shared._guard_company), loaded via the SAME repo the record routes use
(_shared.records_repo.get_by_id), 404 before that guard runs.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repos/service (RecordRepository, OfferRepository, BuyBackService).
Offer invariants (round/status matching, one-pending-offer-per-record,
stale/already-decided-offer rejection) are NOT reimplemented here — they live
in BuyBackService.post_offer / record_decision (Task 8); this route only
translates their ValueError into a 409, mirroring records.py's
cancel_record/reopen_record translation of service.transition's ValueError.
"""
from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from core.roles.decorators import v2_permission_required

# Offer rounds the service recognizes (BuyBackService._ROUND_REQUIRED_STATUS).
# Validated here too so a missing/garbage offer_type 400s before it reaches
# the service — the service itself also guards this (raises ValueError ->
# 409 via post_offer's `Unknown offer_type` branch), so this is a fast-path
# 400 for the common "forgot the field" case, not a substitute for that guard.
_OFFER_TYPES = ('initial', 'final')


# ═══════════════════════════════════════════════
# POST OFFER
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/offers', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'offer', 'manage')
def post_offer(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    offer_type = data.get('offer_type')
    if offer_type not in _OFFER_TYPES:
        return jsonify({
            'success': False,
            'error': f"offer_type is required and must be one of {_OFFER_TYPES!r}",
        }), 400

    try:
        offer = _shared.service.post_offer(record, offer_type, data, current_user.id)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409

    return jsonify({'success': True, 'offer': _shared._serialize(offer)}), 201


# ═══════════════════════════════════════════════
# RECORD DECISION
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/offers/<int:offer_id>/decision', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def record_decision(record_id, offer_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    decision = data.get('decision')

    try:
        updated = _shared.service.record_decision(
            record, offer_id, decision, current_user.id, data.get('decline_reason'),
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409

    return jsonify({'success': True, 'record': _shared._serialize(updated)})
