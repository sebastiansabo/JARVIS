"""Invoice <-> DMS document linking routes."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from . import invoices_bp
from .repositories import InvoiceDmsLinkRepository

logger = logging.getLogger('jarvis.invoices.routes.dms_links')

_dms_link_repo = InvoiceDmsLinkRepository()


@invoices_bp.route('/api/invoices/<int:invoice_id>/dms-documents', methods=['GET'])
@login_required
def api_get_invoice_dms_docs(invoice_id):
    """List DMS documents linked to an invoice."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    docs = _dms_link_repo.get_by_invoice(invoice_id)
    return jsonify({'documents': docs})


@invoices_bp.route('/api/invoices/<int:invoice_id>/dms-documents', methods=['POST'])
@login_required
def api_link_invoice_dms_doc(invoice_id):
    """Link a DMS document to an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(silent=True) or {}
    document_id = data.get('document_id')
    if not document_id:
        return jsonify({'success': False, 'error': 'document_id is required'}), 400
    link_id = _dms_link_repo.link(invoice_id, document_id, current_user.id)
    if link_id is None:
        return jsonify({'success': False, 'error': 'Document already linked'}), 409
    return jsonify({'success': True, 'id': link_id}), 201


@invoices_bp.route('/api/invoices/<int:invoice_id>/dms-documents/<int:document_id>', methods=['DELETE'])
@login_required
def api_unlink_invoice_dms_doc(invoice_id, document_id):
    """Remove a DMS document link from an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if _dms_link_repo.unlink(invoice_id, document_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@invoices_bp.route('/api/invoices/dms-search', methods=['GET'])
@login_required
def api_search_dms_docs_for_invoice():
    """Search DMS documents for the invoice linking picker."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    docs = _dms_link_repo.search_documents(query=q if q else None, limit=limit)
    return jsonify({'documents': docs})


@invoices_bp.route('/api/dms-documents/<int:document_id>/invoices', methods=['GET'])
@login_required
def api_get_document_invoices(document_id):
    """Get all invoices linked to a DMS document (reverse lookup)."""
    invoices = _dms_link_repo.get_by_document(document_id)
    return jsonify({'invoices': invoices})
