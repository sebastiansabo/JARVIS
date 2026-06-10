"""PDF download routes for foi de parcurs contracts."""
import os
from flask import send_file
from ._shared import foi_parcurs_bp, jsonify, login_required, logger, _fp_repo
from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/pdf/<pdf_type>', methods=['GET'])
@login_required
def api_download_pdf(id, pdf_type):
    if pdf_type not in ('legal', 'custom'):
        return jsonify({'success': False, 'error': 'Invalid PDF type'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    path_field = f'pdf_{pdf_type}_path'
    pdf_path = contract.get(path_field)

    if not pdf_path or not os.path.exists(pdf_path):
        try:
            if pdf_type == 'legal':
                pdf_path = generate_legal_pdf(contract)
            else:
                pdf_path = generate_custom_pdf(contract)
            _fp_repo.execute(
                f'UPDATE foi_de_parcurs SET {path_field} = %s WHERE id = %s',
                (pdf_path, id),
            )
        except Exception as e:
            logger.exception('Failed to generate PDF for contract %s', id)
            return jsonify({'success': False, 'error': str(e)[:200]}), 500

    return send_file(pdf_path, as_attachment=True,
                     download_name=f'foaie-parcurs-{contract["contract_id"]}-{pdf_type}.pdf')
