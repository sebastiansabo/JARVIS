"""Controlling BAB API routes."""
import logging
from datetime import date
from decimal import Decimal

from flask import request, jsonify, send_file
from flask_login import login_required, current_user

from . import controlling_bab_bp
from .repository import BabRepository
from .parser import parse_bab_xlsx
from .calculator import compute_marja_report
from .exporter import export_marja_xlsx
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

import io

logger = logging.getLogger('jarvis.controlling_bab')

_repo = BabRepository()
_perm_repo = PermissionRepository()


def _check_bab_perm(action):
    """Check controlling.bab.{action} V2 permission."""
    if getattr(current_user, 'is_admin', False):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'controlling', 'bab', action)
    return perm.get('has_permission', False)


# ── Import ──

@controlling_bab_bp.route('/controlling/bab/api/import', methods=['POST'])
@login_required
@handle_api_errors
def api_import_bab():
    """Import BAB xlsx for a period. Handles first import and re-import."""
    if not _check_bab_perm('add'):
        return error_response('Permission denied', 403)

    file = request.files.get('file')
    if not file:
        return error_response('File is required', 400)

    filename = file.filename or ''
    if not filename.lower().endswith('.xlsx'):
        return error_response('Only .xlsx files are accepted', 415)

    try:
        period_year = int(request.form.get('period_year', 0))
        period_month = int(request.form.get('period_month', 0))
        company_id = int(request.form.get('company_id', 0))
    except (ValueError, TypeError):
        return error_response('period_year, period_month, and company_id are required integers', 400)

    if not (1 <= period_month <= 12) or period_year < 2000 or company_id <= 0:
        return error_response('Invalid period or company_id', 400)

    # Check for locked period
    existing = _repo.get_upload_by_period(company_id, period_year, period_month)
    if existing and existing.get('locked_at'):
        return error_response(f'Period {period_month}/{period_year} is locked', 423)

    # Parse xlsx
    file_bytes = file.read()
    entries = parse_bab_xlsx(file_bytes)

    if not entries:
        return error_response('No valid entries found in BAB file', 400)

    if existing:
        # Re-import: delete old entries, insert new, update upload
        _repo.delete_entries(existing['id'])
        _repo.insert_entries(existing['id'], company_id, entries)
        upload = _repo.reimport_upload(existing['id'], filename, current_user.id, len(entries))
        logger.info(f'BAB re-import: company={company_id} period={period_year}-{period_month} '
                     f'rows={len(entries)} import_count={upload["import_count"]}')
    else:
        # First import
        upload = _repo.create_upload(company_id, period_year, period_month,
                                     filename, current_user.id, len(entries))
        _repo.insert_entries(upload['id'], company_id, entries)
        logger.info(f'BAB import: company={company_id} period={period_year}-{period_month} rows={len(entries)}')

    return jsonify({
        'success': True,
        'upload_id': upload['id'],
        'period': f'{period_year}-{period_month:02d}',
        'status': upload['status'],
        'import_count': upload['import_count'],
        'row_count': len(entries),
    })


# ── Periods (12-month grid) ──

@controlling_bab_bp.route('/controlling/bab/api/periods', methods=['GET'])
@login_required
@handle_api_errors
def api_get_periods():
    """Return 12-month rolling grid with status and marja KPI."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    uploads = _repo.get_periods(company_id)
    upload_map = {}
    for u in uploads:
        key = (u['period_year'], u['period_month'])
        upload_map[key] = u

    # Build 12-month grid (current month + 11 prior)
    today = date.today()
    periods = []
    for i in range(11, -1, -1):
        # Calculate month offset
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1

        key = (year, month)
        upload = upload_map.get(key)

        if upload is None:
            periods.append({
                'year': year, 'month': month,
                'status': 'MISSING',
            })
        elif upload.get('locked_at'):
            entry = {
                'year': year, 'month': month,
                'status': 'LOCKED',
                'upload_id': upload['id'],
                'import_count': upload['import_count'],
                'filename': upload['filename'],
                'uploaded_at': str(upload['uploaded_at']) if upload.get('uploaded_at') else None,
            }
            # Compute marja KPI
            marja = _compute_marja_kpi(upload['id'], company_id, year, month)
            if marja is not None:
                entry['marja_finala_lei'] = float(marja['lei'])
                entry['marja_finala_eur'] = float(marja['eur'])
            periods.append(entry)
        else:
            entry = {
                'year': year, 'month': month,
                'status': 'IMPORTED',
                'upload_id': upload['id'],
                'import_count': upload['import_count'],
                'filename': upload['filename'],
                'uploaded_at': str(upload['uploaded_at']) if upload.get('uploaded_at') else None,
            }
            marja = _compute_marja_kpi(upload['id'], company_id, year, month)
            if marja is not None:
                entry['marja_finala_lei'] = float(marja['lei'])
                entry['marja_finala_eur'] = float(marja['eur'])
            periods.append(entry)

    return jsonify({'success': True, 'periods': periods})


def _compute_marja_kpi(upload_id, company_id, year, month):
    """Compute marja_finala for a period, or None if EUR rate missing."""
    rate_row = _repo.get_eur_rate(company_id, year, month)
    if not rate_row:
        return None
    try:
        entries = _repo.get_entries(upload_id)
        config = _repo.get_config(company_id) or None
        report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])), config=config)
        return {'lei': report['marja_finala_lei'], 'eur': report['marja_finala_eur']}
    except Exception:
        return None


# ── Uploads ──

@controlling_bab_bp.route('/controlling/bab/api/uploads', methods=['GET'])
@login_required
@handle_api_errors
def api_list_uploads():
    """List all uploads for a company."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    uploads = _repo.list_uploads(company_id)
    return jsonify({'success': True, 'uploads': uploads})


@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>', methods=['DELETE'])
@login_required
@handle_api_errors
def api_delete_upload(upload_id):
    """Delete an upload. Blocked if period is locked."""
    if not _check_bab_perm('delete'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if upload.get('locked_at'):
        return error_response('Period is locked', 423)

    _repo.delete_upload(upload_id)
    return jsonify({'success': True})


# ── Lock / Unlock ──

@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>/lock', methods=['POST'])
@login_required
@handle_api_errors
def api_lock_upload(upload_id):
    """Lock a period — requires controlling.bab.lock permission."""
    if not _check_bab_perm('lock'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if upload.get('locked_at'):
        return error_response('Already locked', 409)

    result = _repo.lock_upload(upload_id, current_user.id)
    return jsonify({'success': True, 'upload': result})


@controlling_bab_bp.route('/controlling/bab/api/uploads/<int:upload_id>/unlock', methods=['POST'])
@login_required
@handle_api_errors
def api_unlock_upload(upload_id):
    """Unlock a period — requires controlling.bab.lock permission."""
    if not _check_bab_perm('lock'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)
    if not upload.get('locked_at'):
        return error_response('Period is not locked', 409)

    result = _repo.unlock_upload(upload_id, current_user.id)
    return jsonify({'success': True, 'upload': result})


# ── Report ──

@controlling_bab_bp.route('/controlling/bab/api/report/<int:upload_id>', methods=['GET'])
@login_required
@handle_api_errors
def api_get_report(upload_id):
    """Compute and return MarjaReport for an upload."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)

    rate_row = _repo.get_eur_rate(upload['company_id'], upload['period_year'], upload['period_month'])
    if not rate_row:
        return error_response(
            f'EUR rate not set for {upload["period_month"]}/{upload["period_year"]}', 422)

    entries = _repo.get_entries(upload_id)
    config = _repo.get_config(upload['company_id']) or None
    report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])), config=config)

    # Serialize Decimals to float for JSON
    return jsonify({
        'success': True,
        'report': _serialize_report(report),
        'upload': upload,
    })


@controlling_bab_bp.route('/controlling/bab/api/report/<int:upload_id>/export', methods=['GET'])
@login_required
@handle_api_errors
def api_export_report(upload_id):
    """Export MarjaReport as styled xlsx."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)

    rate_row = _repo.get_eur_rate(upload['company_id'], upload['period_year'], upload['period_month'])
    if not rate_row:
        return error_response(
            f'EUR rate not set for {upload["period_month"]}/{upload["period_year"]}', 422)

    entries = _repo.get_entries(upload_id)
    config = _repo.get_config(upload['company_id']) or None
    report = compute_marja_report(entries, Decimal(str(rate_row['eur_rate'])), config=config)
    xlsx_bytes = export_marja_xlsx(report, upload['period_year'], upload['period_month'])

    month_name = ['', 'IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN',
                  'IUL', 'AUG', 'SEP', 'OCT', 'NOI', 'DEC'][upload['period_month']]
    filename = f'Marja_{month_name}{upload["period_year"]}.xlsx'

    return send_file(
        io.BytesIO(xlsx_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )


# ── EUR Rate ──

@controlling_bab_bp.route('/controlling/bab/api/eur-rate/<int:year>/<int:month>', methods=['GET'])
@login_required
@handle_api_errors
def api_get_eur_rate(year, month):
    """Get EUR rate for a period."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)

    rate = _repo.get_eur_rate(company_id, year, month)
    return jsonify({'success': True, 'rate': rate})


@controlling_bab_bp.route('/controlling/bab/api/eur-rate/<int:year>/<int:month>', methods=['PUT'])
@login_required
@handle_api_errors
def api_set_eur_rate(year, month):
    """Set EUR rate for a period."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)

    data = request.get_json()
    if not data or 'eur_rate' not in data or 'company_id' not in data:
        return error_response('company_id and eur_rate are required', 400)

    try:
        eur_rate = Decimal(str(data['eur_rate']))
    except Exception:
        return error_response('Invalid eur_rate value', 400)

    if eur_rate <= 0:
        return error_response('EUR rate must be positive', 400)

    result = _repo.set_eur_rate(data['company_id'], year, month, eur_rate, current_user.id)
    return jsonify({'success': True, 'rate': result})


# ── Companies (for selector) ──

@controlling_bab_bp.route('/controlling/bab/api/companies', methods=['GET'])
@login_required
@handle_api_errors
def api_get_companies():
    """Get companies list for the BAB selector."""
    from database import get_db, get_cursor, release_db, dict_from_row
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('SELECT id, company FROM companies ORDER BY company')
        rows = cursor.fetchall()
        return jsonify({'success': True, 'companies': [dict_from_row(r) for r in rows]})
    finally:
        release_db(conn)


# ── Report Config ──

@controlling_bab_bp.route('/controlling/bab/api/config', methods=['GET'])
@login_required
@handle_api_errors
def api_get_config():
    """Get report config rows for a company."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return error_response('company_id is required', 400)
    rows = _repo.get_config(company_id)
    return jsonify({'success': True, 'config': rows})


@controlling_bab_bp.route('/controlling/bab/api/config', methods=['POST'])
@login_required
@handle_api_errors
def api_add_config_row():
    """Add a single config row."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)
    data = request.get_json()
    if not data:
        return error_response('JSON body required', 400)
    for field in ('company_id', 'kst', 'group_name', 'item_label'):
        if not data.get(field):
            return error_response(f'{field} is required', 400)
    row = _repo.save_config_row(
        data['company_id'], data.get('sort_order', 0), data['kst'],
        data['group_name'], data['item_label'], data.get('konto_list', ''),
        data.get('row_type', 'sum'), data.get('subtotal_of'), data.get('is_main_total', False))
    if data.get('row_type') == 'subtotal' and 'indicator_ids' in data:
        _repo.set_subtotal_refs(row['id'], data['indicator_ids'])
        row['indicator_ids'] = data['indicator_ids']
    return jsonify({'success': True, 'row': row})


@controlling_bab_bp.route('/controlling/bab/api/config/<int:row_id>', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_config_row(row_id):
    """Update a config row."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)
    data = request.get_json()
    if not data:
        return error_response('JSON body required', 400)
    row = _repo.update_config_row(
        row_id, data.get('sort_order', 0), data['kst'],
        data['group_name'], data['item_label'], data.get('konto_list', ''),
        data.get('row_type', 'sum'), data.get('subtotal_of'), data.get('is_main_total', False))
    if data.get('row_type') == 'subtotal' and 'indicator_ids' in data:
        _repo.set_subtotal_refs(row['id'], data['indicator_ids'])
        row['indicator_ids'] = data['indicator_ids']
    return jsonify({'success': True, 'row': row})


@controlling_bab_bp.route('/controlling/bab/api/config/<int:row_id>', methods=['DELETE'])
@login_required
@handle_api_errors
def api_delete_config_row(row_id):
    """Delete a config row."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)
    _repo.delete_config_row(row_id)
    return jsonify({'success': True})


@controlling_bab_bp.route('/controlling/bab/api/config/bulk', methods=['PUT'])
@login_required
@handle_api_errors
def api_replace_config():
    """Replace all config rows for a company."""
    if not _check_bab_perm('edit'):
        return error_response('Permission denied', 403)
    data = request.get_json()
    if not data or 'company_id' not in data or 'rows' not in data:
        return error_response('company_id and rows are required', 400)
    count = _repo.replace_config(data['company_id'], data['rows'])
    return jsonify({'success': True, 'count': count})


# ── AI Analysis ──

@controlling_bab_bp.route('/controlling/bab/api/analyze', methods=['POST'])
@login_required
@handle_api_errors
def api_analyze():
    """AI-powered financial analysis of BAB data."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)
    data = request.get_json()
    if not data or 'company_id' not in data:
        return error_response('company_id is required', 400)

    from .ai_analysis import analyze_bab
    from database import get_db, get_cursor, release_db

    # Get companies list for context
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('SELECT id, company FROM companies ORDER BY company')
        companies = [{'id': r[0], 'company': r[1]} for r in cursor.fetchall()]
    finally:
        release_db(conn)

    result = analyze_bab(
        repo=_repo,
        company_id=data['company_id'],
        companies=companies,
        mode=data.get('mode', 'auto'),
        prompt=data.get('prompt', ''),
        cross_company=data.get('cross_company', False),
    )
    return jsonify({'success': True, **result})


# ── Verification (raw entries by account) ──

@controlling_bab_bp.route('/controlling/bab/api/verification/<int:upload_id>', methods=['GET'])
@login_required
@handle_api_errors
def api_get_verification(upload_id):
    """Return raw BAB entries grouped by konto for verification."""
    if not _check_bab_perm('view'):
        return error_response('Permission denied', 403)

    upload = _repo.get_upload(upload_id)
    if not upload:
        return error_response('Upload not found', 404)

    entries = _repo.get_entries(upload_id)

    # Group by konto
    by_account = {}
    for e in entries:
        konto = e['konto']
        if konto not in by_account:
            by_account[konto] = {
                'konto': konto,
                'konto_bez': e.get('konto_bez', ''),
                'lines': [],
                'total': 0,
            }
        by_account[konto]['lines'].append({
            'kostenstelle': e['kostenstelle'],
            'kst_bez1': e.get('kst_bez1', ''),
            'saldo1': float(e['saldo1']) if hasattr(e['saldo1'], '__float__') else float(str(e['saldo1'])),
        })
        by_account[konto]['total'] += float(e['saldo1']) if hasattr(e['saldo1'], '__float__') else float(str(e['saldo1']))

    # Sort by konto
    accounts = sorted(by_account.values(), key=lambda x: x['konto'])

    return jsonify({
        'success': True,
        'accounts': accounts,
        'total_entries': len(entries),
        'upload': upload,
    })


# ── BNR Rate (auto-fetch) ──

@controlling_bab_bp.route('/controlling/bab/api/bnr-rate', methods=['GET'])
@login_required
@handle_api_errors
def api_get_bnr_rate():
    """Get BNR EUR/RON rate for end of a given month."""
    from datetime import datetime
    from core.services.currency_converter import get_exchange_rate
    import calendar

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return error_response('year and month are required', 400)

    # Get last day of the month
    last_day = calendar.monthrange(year, month)[1]
    rate_date = f'{year}-{month:02d}-{last_day:02d}'

    rate = get_exchange_rate('EUR', rate_date)
    if rate is None:
        return error_response(f'No BNR rate found for {rate_date}', 404)

    return jsonify({
        'success': True,
        'eur_rate': round(rate, 4),
        'rate_date': rate_date,
    })


# ── Helpers ──

def _serialize_report(report):
    """Convert Decimal values to float for JSON serialization."""
    def _conv(v):
        if isinstance(v, Decimal):
            return float(v)
        return v

    serialized = {
        'eur_rate': float(report['eur_rate']),
        'marja_finala_lei': float(report['marja_finala_lei']),
        'marja_finala_eur': float(report['marja_finala_eur']),
        'sections': [],
    }
    for section in report['sections']:
        s = {'section': section['section'], 'rows': []}
        for row in section['rows']:
            s['rows'].append({
                'label': row['label'],
                'lei': float(row['lei']),
                'eur': float(row['eur']),
                'accounts': row['accounts'],
                'kst': row['kst'],
                'row_type': row.get('row_type', 'sum'),
            })
        serialized['sections'].append(s)
    return serialized
