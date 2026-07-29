"""DB CRUD routes for invoices, allocations, bin, and bulk operations."""
from ._shared import *  # noqa: F401, F403


@invoices_bp.route('/api/db/invoices')
@login_required
def api_db_invoices():
    """Get all invoices from database with pagination and optional filters."""
    if not _check_invoice_perm('view'):
        return error_response('You do not have permission to view invoices', 403)

    limit = request.args.get('limit', 10000, type=int)
    offset = request.args.get('offset', 0, type=int)
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    status = request.args.get('status')
    payment_status = request.args.get('payment_status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_allocations = request.args.get('include_allocations', 'false').lower() == 'true'
    archive_view = request.args.get('archive_view', 'active')
    if archive_view not in ('active', 'archived', 'all'):
        archive_view = 'active'

    # Scope-based filtering
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    org_filter = _get_org_filter_for_scope(scope)

    if include_allocations:
        invoices = _invoice_repo.get_all_with_allocations(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status,
            responsible_user_id=responsible_user_id,
            org_filter=org_filter,
            archive_view=archive_view,
        )
    else:
        invoices = _invoice_repo.get_all(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status,
            responsible_user_id=responsible_user_id,
            org_filter=org_filter,
            archive_view=archive_view,
        )
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>')
@login_required
def api_db_invoice_detail(invoice_id):
    """Get invoice with all allocations."""
    if not _check_invoice_perm('view'):
        return error_response('You do not have permission to view invoices', 403)

    invoice = _invoice_repo.get_with_allocations(invoice_id)
    if not invoice:
        return error_response('Invoice not found', 404)

    # Scope check: restrict visibility based on permission scope
    scope = _get_invoice_scope('view')
    if scope == 'own':
        allocations = invoice.get('allocations', [])
        user_ids = {a.get('responsible_user_id') for a in allocations if a}
        if current_user.id not in user_ids:
            return error_response('Invoice not found', 404)
    elif scope == 'department':
        org_filter = _get_org_filter_for_scope(scope)
        if org_filter and not _allocation_repo.invoice_matches_org_filter(invoice_id, org_filter):
            return error_response('Invoice not found', 404)

    return jsonify(invoice)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/preview')
@login_required
def api_db_invoice_preview(invoice_id):
    """In-app e-Factura preview — parses the stored UBL XML locally (no ANAF PDF).

    Same permission + scope gating as the invoice-detail route; keyed by jarvis
    invoice id. 404 if the invoice has no e-Factura content.
    """
    if not _check_invoice_perm('view'):
        return error_response('You do not have permission to view invoices', 403)

    invoice = _invoice_repo.get_with_allocations(invoice_id)
    if not invoice:
        return error_response('Invoice not found', 404)

    # Scope check: restrict visibility based on permission scope (mirrors detail route).
    scope = _get_invoice_scope('view')
    if scope == 'own':
        user_ids = {a.get('responsible_user_id') for a in invoice.get('allocations', []) if a}
        if current_user.id not in user_ids:
            return error_response('Invoice not found', 404)
    elif scope == 'department':
        org_filter = _get_org_filter_for_scope(scope)
        if org_filter and not _allocation_repo.invoice_matches_org_filter(invoice_id, org_filter):
            return error_response('Invoice not found', 404)

    from core.connectors.efactura.services.invoice_xml_service import get_invoice_xml_by_jarvis_id
    xml_content = get_invoice_xml_by_jarvis_id(invoice_id)
    if not xml_content:
        return error_response('No e-Factura content available for this invoice', 404)

    from core.connectors.efactura.invoice_preview import build_invoice_preview
    return jsonify(build_invoice_preview(xml_content))


@invoices_bp.route('/api/db/invoices/archive-counts')
@login_required
def api_db_archive_counts():
    """Get counts for active and archived invoices."""
    if not _check_invoice_perm('view'):
        return error_response('Permission denied', 403)
    counts = _invoice_repo.get_archive_counts()
    return jsonify({'success': True, **counts})


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['DELETE'])
@login_required
def api_db_delete_invoice(invoice_id):
    """Soft delete an invoice (move to bin)."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    if _invoice_repo.delete(invoice_id):
        _service._log_event(_get_user_context(), 'invoice_deleted',
                            f'Moved invoice ID {invoice_id} to bin',
                            entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return error_response('Invoice not found', 404)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/restore', methods=['POST'])
@login_required
def api_db_restore_invoice(invoice_id):
    """Restore a soft-deleted invoice from the bin."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    if _invoice_repo.restore(invoice_id):
        _service._log_event(_get_user_context(), 'invoice_restored',
                            f'Restored invoice ID {invoice_id} from bin',
                            entity_type='invoice', entity_id=invoice_id)
        return jsonify({'success': True})
    return error_response('Invoice not found in bin', 404)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/permanent', methods=['DELETE'])
@login_required
def api_db_permanently_delete_invoice(invoice_id):
    """Permanently delete an invoice. Also deletes from Google Drive."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403

    result = _service.permanently_delete(invoice_id, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/db/invoices/bulk-delete', methods=['POST'])
@login_required
def api_db_bulk_delete_invoices():
    """Soft delete multiple invoices."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return error_response('No invoice IDs provided')
    count = _invoice_repo.bulk_soft_delete(invoice_ids)
    return jsonify({'success': True, 'deleted_count': count})


@invoices_bp.route('/api/db/invoices/bulk-restore', methods=['POST'])
@login_required
def api_db_bulk_restore_invoices():
    """Restore multiple soft-deleted invoices."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to restore invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return error_response('No invoice IDs provided')
    count = _invoice_repo.bulk_restore(invoice_ids)
    return jsonify({'success': True, 'restored_count': count})


@invoices_bp.route('/api/db/invoices/bulk-permanent-delete', methods=['POST'])
@login_required
def api_db_bulk_permanently_delete_invoices():
    """Permanently delete multiple invoices. Also deletes from Google Drive."""
    if not _check_invoice_perm('delete'):
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])
    if not invoice_ids:
        return error_response('No invoice IDs provided')

    result = _service.bulk_permanently_delete(invoice_ids, _get_user_context())
    return jsonify(result.data)


@invoices_bp.route('/api/db/invoices/bin', methods=['GET'])
@login_required
def api_db_get_deleted_invoices():
    """Get all soft-deleted invoices (bin)."""
    if not _check_invoice_perm('view'):
        return error_response('You do not have permission to view invoices', 403)

    invoices = _invoice_repo.get_all(include_deleted=True, limit=500)
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['PUT'])
@login_required
def api_db_update_invoice(invoice_id):
    """Update an invoice."""
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Scope check: restrict editing based on permission scope
    scope = _get_invoice_scope('edit')
    if scope == 'own':
        if not _allocation_repo.user_has_allocation(invoice_id, current_user.id):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
    elif scope == 'department':
        org_filter = _get_org_filter_for_scope(scope)
        if org_filter and not _allocation_repo.invoice_matches_org_filter(invoice_id, org_filter):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    result = _service.update_invoice(invoice_id, data, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/db/invoices/<int:invoice_id>/allocations', methods=['PUT'])
@login_required
def api_db_update_allocations(invoice_id):
    """Update all allocations for an invoice."""
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Scope check: restrict allocation editing based on permission scope
    scope = _get_invoice_scope('edit')
    if scope == 'own':
        if not _allocation_repo.user_has_allocation(invoice_id, current_user.id):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
    elif scope == 'department':
        org_filter = _get_org_filter_for_scope(scope)
        if org_filter and not _allocation_repo.invoice_matches_org_filter(invoice_id, org_filter):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    allocations = data.get('allocations', [])
    send_notification = data.get('send_notification', False)

    if not allocations:
        return jsonify({'success': False, 'error': 'At least one allocation is required'}), 400

    result = _service.update_allocations(invoice_id, allocations, send_notification, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/allocations/<int:allocation_id>/comment', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_allocation_comment(allocation_id):
    """Update the comment for a specific allocation."""
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    comment = data.get('comment', '')

    updated = _allocation_repo.update_comment(allocation_id, comment)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Allocation not found'}), 404
