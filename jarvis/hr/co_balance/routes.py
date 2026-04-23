"""HTTP endpoints for HR CO balance import + read.

Routes mounted under `/hr/co-balance/*` via `co_balance_bp` (blueprint
registered in `jarvis/hr/__init__.py`).
"""

import logging
import threading
import uuid

from flask import request, jsonify
from flask_login import current_user, login_required

from core.utils.api_helpers import api_login_required, safe_error_response
from . import co_balance_bp
from .importer import import_co_balance
from .repository import CoBalanceRepository

logger = logging.getLogger('jarvis.hr.co_balance.routes')

# One import at a time is enough for this use case (a handful of xlsx files).
_import_lock = threading.Lock()


def _require_hr():
    """Inline auth guard: authenticated + can_access_hr.

    Returns a JSON 401/403 Response if forbidden, else None.
    (hr_required decorator in _shared.py redirects; not suitable for JSON APIs.)
    """
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    if not getattr(current_user, 'can_access_hr', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403
    return None


# ── Import ──

@co_balance_bp.route('/api/co-balance/import', methods=['POST'])
@api_login_required
def co_balance_import():
    """Upload one CO-balance xlsx → start a background import.

    Multipart form fields: `file` (xlsx), `year` (int).
    Returns `{run_id}` immediately; poll `/import/status/<run_id>`.
    """
    forbidden = _require_hr()
    if forbidden:
        return forbidden

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Missing file'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'Empty file'}), 400

    year_raw = request.form.get('year')
    try:
        year = int(year_raw) if year_raw else None
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid year'}), 400
    if not year or year < 2000 or year > 2100:
        return jsonify({'success': False, 'error': 'Year must be between 2000 and 2100'}), 400

    file_bytes = f.read()
    filename = f.filename
    imported_by = current_user.id

    run_id = str(uuid.uuid4())
    repo = CoBalanceRepository()
    repo.create_import_run(run_id, year, filename, imported_by)

    def _run(file_bytes, filename, year, imported_by, run_id):
        acquired = _import_lock.acquire(blocking=True, timeout=300)
        repo = CoBalanceRepository()
        try:
            if not acquired:
                repo.finish_import_run(
                    run_id, status='failed',
                    rows_total=0, rows_matched=0, rows_unmatched=0,
                    companies='', error_message='Import lock timeout',
                )
                return
            result = import_co_balance(file_bytes, filename, year, imported_by)
            repo.finish_import_run(
                run_id,
                status='completed',
                rows_total=result['rows_total'],
                rows_matched=result['rows_matched'],
                rows_unmatched=result['rows_unmatched'],
                companies=','.join(result['companies']),
                error_message='\n'.join(result['errors']) if result['errors'] else None,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception('CO balance import crashed')
            try:
                repo.finish_import_run(
                    run_id, status='failed',
                    rows_total=0, rows_matched=0, rows_unmatched=0,
                    companies='', error_message=str(e),
                )
            except Exception:
                logger.exception('Failed to record import failure')
        finally:
            if acquired:
                _import_lock.release()

    threading.Thread(
        target=_run,
        args=(file_bytes, filename, year, imported_by, run_id),
        daemon=True,
    ).start()

    return jsonify({'success': True, 'run_id': run_id})


@co_balance_bp.route('/api/co-balance/import/status/<run_id>', methods=['GET'])
@api_login_required
def co_balance_import_status(run_id):
    """Poll a background import. Returns the row from sincron_co_import_runs."""
    forbidden = _require_hr()
    if forbidden:
        return forbidden

    try:
        row = CoBalanceRepository().get_import_run(run_id)
        if not row:
            return jsonify({'success': False, 'error': 'Unknown run_id'}), 404
        return jsonify({'success': True, 'data': row})
    except Exception as e:  # noqa: BLE001
        return safe_error_response(e)


# ── Read ──

@co_balance_bp.route('/api/co-balance', methods=['GET'])
@api_login_required
def co_balance_get_year():
    """Return CO balance for a given year, keyed by mapped JARVIS user_id.

    Also returns used_ytd (from sincron_timesheets) and current_balance.
    """
    forbidden = _require_hr()
    if forbidden:
        return forbidden

    try:
        year = int(request.args.get('year'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Missing/invalid year'}), 400

    repo = CoBalanceRepository()
    all_rows = repo.get_all_for_year(year)
    used_by_company = repo.get_used_ytd_by_user_company(year)
    used_by_user = repo.get_used_ytd_by_user(year)
    out = {}
    for row in all_rows:
        uid = row['user_id']
        company = row['company_name']
        # Per-company used from timesheets (normalized match)
        user_used = used_by_company.get(uid, {})
        # Try exact match first, then normalized
        used = user_used.get(company, None)
        if used is None:
            norm = company.upper().replace(' S.R.L.', '').replace(' SRL', '').strip()
            for k, v in user_used.items():
                if k.upper().replace(' S.R.L.', '').replace(' SRL', '').strip() == norm:
                    used = v
                    break
        if used is None:
            used = 0
        used = int(round(used))
        total = int(row.get('total_available') or 0)
        key = f"{uid}_{row['id']}"
        out[key] = {
            'id': row['id'],
            'user_id': uid,
            'year': row['year'],
            'company_name': company,
            'cnp': row['cnp'],
            'nume': row['nume'],
            'prenume': row['prenume'],
            'departament': row['departament'],
            'carry_prev_year': int(row['carry_prev_year'] or 0),
            'carry_two_years_ago': int(row['carry_two_years_ago'] or 0),
            'annual_cim': int(row['annual_cim'] or 0),
            'seniority_bonus': int(row['seniority_bonus'] or 0),
            'manual_adjustment': int(row['manual_adjustment'] or 0),
            'total_available': total,
            'used_ytd': used,
            'current_balance': total - used,
        }
    return jsonify({'success': True, 'year': year, 'data': out})


@co_balance_bp.route('/api/co-balance', methods=['DELETE'])
@api_login_required
def co_balance_delete():
    """Delete CO balance rows by their database IDs."""
    forbidden = _require_hr()
    if forbidden:
        return forbidden
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'No IDs provided'}), 400
    repo = CoBalanceRepository()
    deleted = repo.delete_rows(ids)
    return jsonify({'success': True, 'deleted': deleted})


@co_balance_bp.route('/api/co-balance/unmatched', methods=['GET'])
@api_login_required
def co_balance_unmatched():
    """List rows for `year` whose CNP didn't auto-match a JARVIS user."""
    forbidden = _require_hr()
    if forbidden:
        return forbidden

    try:
        year = int(request.args.get('year'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Missing/invalid year'}), 400

    try:
        rows = CoBalanceRepository().unmatched_for_year(year)
        return jsonify({'success': True, 'year': year, 'data': rows})
    except Exception as e:  # noqa: BLE001
        return safe_error_response(e)


@co_balance_bp.route('/api/co-balance/unmatched/<int:row_id>/assign', methods=['POST'])
@api_login_required
def co_balance_assign(row_id):
    """Manually map an unmatched CO-balance row to a JARVIS user."""
    forbidden = _require_hr()
    if forbidden:
        return forbidden

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id required'}), 400

    try:
        CoBalanceRepository().assign_user(row_id, int(user_id))
        return jsonify({'success': True})
    except Exception as e:  # noqa: BLE001
        return safe_error_response(e)


@co_balance_bp.route('/api/co-balance/imports', methods=['GET'])
@api_login_required
def co_balance_list_imports():
    """Recent import runs (for Settings UI history)."""
    forbidden = _require_hr()
    if forbidden:
        return forbidden
    try:
        limit = int(request.args.get('limit', 20))
    except ValueError:
        limit = 20
    try:
        rows = CoBalanceRepository().list_import_runs(limit=limit)
        return jsonify({'success': True, 'data': rows})
    except Exception as e:  # noqa: BLE001
        return safe_error_response(e)
