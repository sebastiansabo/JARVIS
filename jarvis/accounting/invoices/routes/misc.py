"""Miscellaneous routes: drive-link and store-to-dms."""
from ._shared import *  # noqa: F401, F403


@invoices_bp.route('/api/invoices/<int:invoice_id>/drive-link', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_invoice_drive_link(invoice_id):
    """Update only the drive_link for an invoice."""
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    drive_link = data.get('drive_link')

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    updated = _invoice_repo.update(invoice_id=invoice_id, drive_link=drive_link)
    if updated:
        return jsonify({'success': True})
    return error_response('Invoice not found', 404)


@invoices_bp.route('/api/invoices/store-to-dms', methods=['POST'])
@login_required
@handle_api_errors
def api_store_invoices_to_dms():
    """Store one or more invoices into DMS folder structure.

    Creates a DMS document for each invoice in: Company > Year > Facturi.
    If invoice has tags, creates tag subfolders under Facturi.
    Auto-links the created DMS document to the invoice.

    Body: { invoice_ids: [1, 2, 3] }
    """
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return jsonify({'success': False, 'error': 'invoice_ids required'}), 400

    from dms.repositories import DocumentRepository, CategoryRepository
    from dms.services.folder_sync_service import FolderSyncService
    from core.tags.repositories.tag_repository import TagRepository

    doc_repo = DocumentRepository()
    cat_repo = CategoryRepository()
    folder_sync = FolderSyncService()
    tag_repo = TagRepository()
    dms_link_repo = InvoiceDmsLinkRepository()

    # Find "Facturi" category
    facturi_cat = dms_link_repo.get_facturi_category()
    category_id = facturi_cat['id'] if facturi_cat else None
    category_name = facturi_cat['name'] if facturi_cat else 'Facturi'
    category_icon = facturi_cat.get('icon', 'bi-folder') if facturi_cat else 'bi-folder'
    category_color = facturi_cat.get('color', '#6c757d') if facturi_cat else '#6c757d'

    stored = []
    skipped = []
    errors = []

    for inv_id in invoice_ids:
        try:
            # Get invoice with allocations
            inv = _invoice_repo.get_with_allocations(inv_id)
            if not inv:
                errors.append({'id': inv_id, 'error': 'Invoice not found'})
                continue

            # Check if already stored (has a linked DMS doc with metadata.source = 'store_to_dms')
            existing = dms_link_repo.get_stored_dms_doc(inv_id)
            if existing:
                skipped.append({'id': inv_id, 'reason': 'already_stored', 'document_id': existing['document_id']})
                continue

            # Resolve company from allocations or fallback to current user
            company_id = dms_link_repo.get_company_id_for_invoice(inv_id) or current_user.company_id

            if not company_id:
                errors.append({'id': inv_id, 'error': 'Could not resolve company'})
                continue

            # Resolve folder: Company > Year > Facturi > Month
            folder_id = folder_sync.resolve_document_folder(
                company_id=company_id,
                doc_date=inv.get('invoice_date'),
                category_name=category_name,
                category_id=category_id,
                category_icon=category_icon,
                category_color=category_color,
                created_by=current_user.id,
                include_month=True,
            )

            # Handle tag subfolders: if invoice has tags, place doc in tag subfolder
            tags = tag_repo.get_entity_tags('invoice', inv_id, current_user.id)
            target_folder_id = folder_id
            tag_names = []

            if tags and folder_id:
                # Use first tag as subfolder under month (depth=4)
                primary_tag = tags[0]
                tag_names = [t['name'] for t in tags]
                parent_path = dms_link_repo.get_folder_path(folder_id)
                tag_subfolder = folder_sync._ensure_child(
                    parent_id=folder_id,
                    parent_path=parent_path['path'],
                    name=primary_tag['name'],
                    company_id=company_id,
                    depth=parent_path['depth'] + 1,
                    sort_order=0,
                    icon='bi-tag',
                    color=primary_tag.get('color') or '#6c757d',
                    created_by=current_user.id,
                )
                target_folder_id = tag_subfolder['id']

            # Create DMS document
            title = f"Factura {inv.get('invoice_number', '')} - {inv.get('supplier', '')}"
            metadata = {
                'source': 'store_to_dms',
                'invoice_id': inv_id,
                'supplier': inv.get('supplier'),
                'invoice_number': inv.get('invoice_number'),
                'invoice_value': str(inv.get('invoice_value', '')),
                'currency': inv.get('currency'),
                'tags': tag_names,
            }

            doc = doc_repo.create(
                title=title,
                company_id=company_id,
                created_by=current_user.id,
                category_id=category_id,
                status='active',
                doc_number=inv.get('invoice_number'),
                doc_date=inv.get('invoice_date'),
                metadata=str(metadata).replace("'", '"'),
            )

            # Set folder_id on the document
            if target_folder_id:
                dms_link_repo.set_document_folder(doc['id'], target_folder_id)

            # Auto-link the DMS document to the invoice
            dms_link_repo.link(inv_id, doc['id'], current_user.id)

            stored.append({
                'invoice_id': inv_id,
                'document_id': doc['id'],
                'folder_id': target_folder_id,
                'title': title,
            })

        except Exception as e:
            logger.exception('Failed to store invoice %d to DMS', inv_id)
            errors.append({'id': inv_id, 'error': str(e)})

    return jsonify({
        'success': True,
        'stored': len(stored),
        'skipped': len(skipped),
        'errors': len(errors),
        'details': {
            'stored': stored,
            'skipped': skipped,
            'errors': errors,
        }
    })
