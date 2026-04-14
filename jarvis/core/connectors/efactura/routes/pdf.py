"""
e-Factura PDF generation API routes.
"""
from flask import request, jsonify, Response

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required
from ..services.pdf_service import PDFService

_pdf_service = PDFService()


# ============================================================
# API: PDF Operations
# ============================================================

@efactura_bp.route('/api/invoices/<int:invoice_id>/pdf', methods=['GET'])
@api_login_required
@efactura_access_required
def get_invoice_pdf(invoice_id: int):
    """
    Get PDF for a stored e-Factura invoice.

    Retrieves the XML from storage and converts to PDF via ANAF API.
    """
    try:
        result = _pdf_service.get_invoice_pdf(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return Response(
            result.data['pdf_data'],
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={result.data["filename"]}',
            }
        )

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/anaf/export-pdf/<message_id>', methods=['GET'])
@api_login_required
@efactura_access_required
def export_invoice_pdf(message_id: str):
    """
    Export invoice as PDF.

    Downloads the ZIP from ANAF, extracts the XML, and converts it to PDF
    using ANAF's official XML-to-PDF transformation API.

    Query params:
        cif: Company CIF (required)
        standard: 'FACT1' (invoice) or 'FCN' (credit note), default 'FACT1'
        validate: 'true' or 'false', default 'true'
    """
    try:
        cif = request.args.get('cif')
        standard = request.args.get('standard', 'FACT1')
        validate = request.args.get('validate', 'true').lower() == 'true'

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        if standard not in ('FACT1', 'FCN'):
            return jsonify({
                'success': False,
                'error': "Invalid standard. Must be 'FACT1' or 'FCN'",
            }), 400

        result = _pdf_service.export_anaf_pdf(cif, message_id, standard, validate)

        if not result.success:
            status_code = 400 if 'Configuration' in (result.error or '') else 500
            return jsonify({
                'success': False,
                'error': result.error,
            }), status_code

        return Response(
            result.data['pdf_data'],
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={result.data["filename"]}',
                'X-Mock-Mode': str(result.data['mock_mode']).lower(),
            }
        )

    except Exception as e:
        return safe_error_response(e)
