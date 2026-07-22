"""Bulk driving-session import: Excel template download + upload/parse."""
import io
from flask import send_file
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..services.session_import_service import build_template_xlsx, import_sessions

_XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@foi_parcurs_bp.route('/api/foi-parcurs/sessions/import-template', methods=['GET'])
@login_required
def api_session_import_template():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        content = build_template_xlsx(company_id)
    except Exception as e:
        logger.exception('Session import template failed for %s', company_id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return send_file(io.BytesIO(content), mimetype=_XLSX_MIME, as_attachment=True,
                     download_name=f'import-sesiuni-{company_id}.xlsx')


@foi_parcurs_bp.route('/api/foi-parcurs/sessions/import', methods=['POST'])
@login_required
def api_session_import():
    company_id = request.form.get('company_id', type=int)
    file = request.files.get('file')
    if not company_id or file is None:
        return jsonify({'success': False, 'error': 'company_id și file sunt obligatorii'}), 400
    try:
        report = import_sessions(
            company_id, file.read(),
            user_name=(getattr(current_user, 'name', None) or getattr(current_user, 'email', None)))
    except Exception as e:
        logger.exception('Session import failed for company %s', company_id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500
    return jsonify({'success': True, **report})
