"""PDF download + email routes for foi de parcurs contracts."""
import os
import re
from flask import send_file
from ._shared import foi_parcurs_bp, jsonify, request, login_required, logger, _fp_repo
from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _ensure_pdf_path(contract, contract_id, pdf_type):
    """Return the on-disk path for the contract's PDF, generating + persisting it
    if missing. Raises on generation failure."""
    path_field = f'pdf_{pdf_type}_path'
    pdf_path = contract.get(path_field)
    if not pdf_path or not os.path.exists(pdf_path):
        pdf_path = generate_legal_pdf(contract) if pdf_type == 'legal' else generate_custom_pdf(contract)
        _fp_repo.execute(
            f'UPDATE foi_de_parcurs SET {path_field} = %s WHERE id = %s',
            (pdf_path, contract_id),
        )
    return pdf_path


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/pdf/<pdf_type>', methods=['GET'])
@login_required
def api_download_pdf(id, pdf_type):
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    try:
        pdf_path = _ensure_pdf_path(contract, id, pdf_type)
    except Exception as e:
        logger.exception('Failed to generate PDF for contract %s', id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500

    return send_file(pdf_path, as_attachment=True,
                     download_name=f'foaie-parcurs-{contract["contract_id"]}-{pdf_type}.pdf')


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/email', methods=['POST'])
@login_required
def api_email_pdf(id):
    """Email the contract PDF (default: legal) to a recipient. Body:
    {"to_email": "...", "pdf_type": "legal"|"custom"}. If to_email is omitted,
    falls back to the client's email on file."""
    data = request.get_json(silent=True) or {}
    pdf_type = (data.get('pdf_type') or 'legal').strip()
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    to_email = (data.get('to_email') or contract.get('client_email') or '').strip()
    if not to_email or not _EMAIL_RE.match(to_email):
        return jsonify({'success': False, 'error': 'Adresă de email invalidă sau lipsă.'}), 400

    try:
        pdf_path = _ensure_pdf_path(contract, id, pdf_type)
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
    except Exception as e:
        logger.exception('Failed to generate PDF for contract %s', id)
        return jsonify({'success': False, 'error': str(e)[:200]}), 500

    from core.services.notification_service import send_email, is_smtp_configured
    if not is_smtp_configured():
        return jsonify({'success': False, 'error': 'Trimiterea de email nu este configurată.'}), 503

    contract_code = contract.get('contract_id') or id
    client_name = contract.get('client_name') or ''
    filename = f'foaie-parcurs-{contract_code}.pdf'
    html_body = (
        f'<p>Bună ziua{(" " + client_name) if client_name else ""},</p>'
        f'<p>Atașat găsiți contractul de test drive ({contract_code}).</p>'
        f'<p>O zi bună,<br>AUTOWORLD</p>'
    )
    ok, err = send_email(
        to_email=to_email,
        subject=f'Foaie de parcurs {contract_code} — AUTOWORLD',
        html_body=html_body,
        attachments=[(filename, pdf_bytes)],
        from_name='AUTOWORLD',
    )
    if not ok:
        logger.error('Failed to email contract %s to %s: %s', id, to_email, err)
        return jsonify({'success': False, 'error': err or 'Trimiterea a eșuat.'}), 502

    return jsonify({'success': True, 'sent_to': to_email})
