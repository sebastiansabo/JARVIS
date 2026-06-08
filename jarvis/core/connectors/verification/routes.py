"""Verification API routes."""

import logging
import threading
from flask import request, jsonify
from flask_login import current_user

from . import verification_bp
from .verification_service import VerificationService
from core.utils.api_helpers import api_login_required, safe_error_response

logger = logging.getLogger('jarvis.verification.routes')
service = VerificationService()
_run_lock = threading.Lock()


def _require_hr():
    """Return a 403 response if user is not HR/admin, else None."""
    if not getattr(current_user, 'can_access_hr', False) and \
       not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403
    return None


@verification_bp.route('/api/run', methods=['POST'])
@api_login_required
def run_verification():
    """Trigger a verification run for a given year/month."""
    err = _require_hr()
    if err:
        return err

    data = request.get_json() or {}
    year = data.get('year')
    month = data.get('month')

    if not year or not month:
        from datetime import datetime
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    if not _run_lock.acquire(blocking=False):
        return jsonify({'success': False, 'error': 'A verification run is already in progress'}), 409

    try:
        result = service.run_verification(
            year=int(year),
            month=int(month),
            triggered_by=current_user.id,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)
    finally:
        _run_lock.release()


@verification_bp.route('/api/results', methods=['GET'])
@api_login_required
def get_results():
    """Get discrepancies for the last (or specified) verification run."""
    err = _require_hr()
    if err:
        return err

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    include_resolved = request.args.get('include_resolved', 'false').lower() == 'true'

    if not year or not month:
        from datetime import datetime
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    last_run = service.get_last_run(year, month)
    if not last_run:
        return jsonify({'success': True, 'run': None, 'data': []})

    discrepancies = service.get_discrepancies(last_run['run_id'], include_resolved)

    # Serialize dates
    for d in discrepancies:
        if d.get('day'):
            d['day'] = str(d['day'])
        for ts_field in ('created_at', 'resolved_at'):
            if d.get(ts_field):
                d[ts_field] = str(d[ts_field])

    run_out = dict(last_run)
    for ts_field in ('started_at', 'finished_at'):
        if run_out.get(ts_field):
            run_out[ts_field] = str(run_out[ts_field])

    return jsonify({'success': True, 'run': run_out, 'data': discrepancies})


@verification_bp.route('/api/resolve/<int:discrepancy_id>', methods=['POST'])
@api_login_required
def resolve_discrepancy(discrepancy_id):
    """Mark a discrepancy as resolved."""
    err = _require_hr()
    if err:
        return err

    data = request.get_json() or {}
    notes = data.get('notes', '')

    resolved = service.resolve_discrepancy(discrepancy_id, current_user.id, notes)
    if not resolved:
        return jsonify({'success': False, 'error': 'Discrepancy not found or already resolved'}), 404

    return jsonify({'success': True})
