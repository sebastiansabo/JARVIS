"""Hold/Resume routes — put an active buyback record ON_HOLD (pending
missing info from the submitter) and take it off hold again, restoring the
exact status it was held from.

Both routes are gated by @v2_permission_required('buyback', 'record', 'hold')
plus the same company-scoping/IDOR guard every other single-record mutation
here uses (_shared._guard_company) — a company-A caller may not hold/resume
a company-B record even if they can guess its id.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton repo/service (RecordRepository, BuyBackService). The actual
hold/resume bookkeeping (status flip, hold_* column stamping/clearing, audit
event) lives in BuyBackService.hold/.resume; this module only validates the
request body and translates ValueError (illegal state) into a 409.

Notifying the issuer (email + in-app/push) on hold is best-effort and runs
AFTER the hold is already committed — see
buyback.services.notifications.notify_held, which swallows its own
exceptions. A raising notifier must never turn an otherwise-successful hold
into an error response (hence the broad `except Exception` around the call
here, on top of notify_held's own internal swallowing).
"""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from buyback.services.notifications import notify_held
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.buyback')


# ═══════════════════════════════════════════════
# HOLD
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/hold', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'hold')
def hold_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    reason = data.get('reason')
    if not _shared.is_nonempty_str(reason):
        return jsonify({'success': False, 'error': 'reason is required'}), 400
    note = data.get('note')
    if note is not None and not isinstance(note, str):
        return jsonify({'success': False, 'error': 'note must be a string'}), 400

    try:
        updated = _shared.service.hold(record, reason, note, current_user.id)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409

    # Best-effort issuer notification (email + in-app/push) — never let a
    # notifier failure turn an already-committed hold into an error response.
    try:
        notify_held(updated, reason, note, current_user.id)
    except Exception:
        logger.warning(
            'notify_held failed for buyback record %s — hold still succeeded',
            record_id, exc_info=True,
        )

    return jsonify({'success': True, 'record': _shared._serialize(updated)})


# ═══════════════════════════════════════════════
# RESUME
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/resume', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'hold')
def resume_record(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    try:
        updated = _shared.service.resume(record, current_user.id)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 409

    return jsonify({'success': True, 'record': _shared._serialize(updated)})
