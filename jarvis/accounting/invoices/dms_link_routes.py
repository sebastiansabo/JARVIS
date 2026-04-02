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


@invoices_bp.route('/api/invoices/<int:invoice_id>/upload-and-link', methods=['POST'])
@login_required
def api_upload_and_link(invoice_id):
    """Quick upload: create DMS document from files, place in invoice folder, and link."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    files = request.files.getlist('files') or ([request.files['file']] if 'file' in request.files else [])
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    import json
    from dms.repositories import DocumentRepository
    from dms.services.document_service import DocumentService, MAX_FILE_SIZE
    from dms.services.folder_sync_service import FolderSyncService

    _doc_repo = DocumentRepository()
    _doc_svc = DocumentService()
    _folder_sync = FolderSyncService()

    # Get invoice info
    inv = _dms_link_repo.query_one(
        'SELECT id, invoice_number, supplier, invoice_date FROM invoices WHERE id = %s',
        (invoice_id,)
    )
    if not inv:
        return jsonify({'success': False, 'error': 'Invoice not found'}), 404

    # Resolve company_id from allocations (same pattern as store-to-dms)
    company_id = None
    alloc_row = _dms_link_repo.query_one(
        'SELECT company FROM allocations WHERE invoice_id = %s LIMIT 1',
        (invoice_id,)
    )
    if alloc_row and alloc_row.get('company'):
        comp_row = _dms_link_repo.query_one(
            'SELECT id FROM companies WHERE company = %s', (alloc_row['company'],)
        )
        if comp_row:
            company_id = comp_row['id']
    if not company_id:
        company_id = current_user.company_id

    # Get "Facturi" category
    cat_row = _dms_link_repo.query_one(
        "SELECT id, name, icon, color FROM dms_categories WHERE slug = 'facturi'"
    )
    category_id = cat_row['id'] if cat_row else None
    category_name = cat_row['name'] if cat_row else 'Facturi'
    category_icon = cat_row['icon'] if cat_row else 'bi-folder'
    category_color = cat_row['color'] if cat_row else '#6c757d'

    # Resolve DMS folder: Company > Year > Facturi > Month
    folder_id = None
    if company_id:
        folder_id = _folder_sync.resolve_document_folder(
            company_id=company_id,
            doc_date=inv.get('invoice_date'),
            category_name=category_name,
            category_id=category_id,
            category_icon=category_icon,
            category_color=category_color,
            created_by=current_user.id,
            include_month=True,
        )

    # Auto-store invoice to DMS if not already stored
    stored_invoice_doc = None
    existing_store = _dms_link_repo.query_one('''
        SELECT l.document_id FROM invoice_dms_links l
        JOIN dms_documents d ON d.id = l.document_id
        WHERE l.invoice_id = %s AND d.deleted_at IS NULL
          AND d.metadata->>'source' = 'store_to_dms'
    ''', (invoice_id,))

    if not existing_store:
        try:
            inv_title = f"Factura {inv.get('invoice_number', '')} - {inv.get('supplier', '')}"
            inv_meta = {
                'source': 'store_to_dms',
                'invoice_id': invoice_id,
                'supplier': inv.get('supplier'),
                'invoice_number': inv.get('invoice_number'),
            }
            inv_doc = _doc_repo.create(
                title=inv_title,
                company_id=company_id,
                category_id=category_id,
                folder_id=folder_id,
                status='active',
                created_by=current_user.id,
                doc_number=inv.get('invoice_number'),
                doc_date=inv.get('invoice_date'),
                metadata=json.dumps(inv_meta),
            )
            _dms_link_repo.link(invoice_id, inv_doc['id'], current_user.id)
            stored_invoice_doc = inv_doc['id']
            logger.info('Auto-stored invoice %d to DMS doc %d', invoice_id, inv_doc['id'])
        except Exception as e:
            logger.warning('Auto-store invoice %d to DMS failed: %s', invoice_id, e)

    created_docs = []
    errors = []

    for f in files:
        try:
            file_bytes = f.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                errors.append({'file': f.filename, 'error': 'File too large (max 25MB)'})
                continue

            inv_num = inv.get('invoice_number') or str(invoice_id)
            title = f"Factura {inv_num} - {f.filename}"

            doc_result = _doc_repo.create(
                title=title,
                company_id=company_id,
                category_id=category_id,
                folder_id=folder_id,
                status='active',
                created_by=current_user.id,
                metadata=json.dumps({'source': 'invoice_upload', 'invoice_id': invoice_id}),
            )
            doc_id = doc_result['id']

            _doc_svc.upload_file(doc_id, file_bytes, f.filename, current_user.id)
            _dms_link_repo.link(invoice_id, doc_id, current_user.id)
            created_docs.append({'document_id': doc_id, 'title': title, 'file': f.filename})

        except Exception as e:
            logger.exception('upload-and-link failed for %s', f.filename)
            errors.append({'file': f.filename, 'error': str(e)[:200]})

    return jsonify({
        'success': len(created_docs) > 0,
        'documents': created_docs,
        'errors': errors,
        'stored_invoice_doc_id': stored_invoice_doc,
    }), 201 if created_docs else 400
