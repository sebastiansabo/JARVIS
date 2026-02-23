"""Invoice, allocation, and summary API routes."""
import os
from flask import jsonify, request, redirect
from flask_login import login_required, current_user

from . import invoices_bp
from .repositories import InvoiceRepository, AllocationRepository, SummaryRepository
from .services import InvoiceService
from .services.invoice_service import UserContext
from core.utils.api_helpers import error_response, safe_error_response, handle_api_errors

_invoice_repo = InvoiceRepository()
_allocation_repo = AllocationRepository()
_summary_repo = SummaryRepository()
_service = InvoiceService()


def _get_user_context() -> UserContext:
    """Build UserContext from Flask globals."""
    return UserContext(
        user_id=current_user.id,
        user_email=current_user.email,
        role_name=current_user.role_name,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500],
    )


# ============== PAGE ROUTES ==============

@invoices_bp.route('/add-invoice')
@login_required
def add_invoice():
    """Redirect to React add invoice page."""
    return redirect('/app/accounting/add')


@invoices_bp.route('/accounting')
@login_required
def accounting():
    """Redirect to React accounting dashboard."""
    return redirect('/app/accounting')


# ============== INVOICE SUBMISSION ==============

@invoices_bp.route('/api/submit', methods=['POST'])
@login_required
def submit_invoice():
    """Submit an invoice with its cost distribution."""
    if not current_user.can_add_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to add invoices'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    result = _service.submit_invoice(data, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ============== INVOICE PARSING ==============

@invoices_bp.route('/api/parse-invoice', methods=['POST'])
@login_required
def api_parse_invoice():
    """Parse an uploaded invoice using AI or template (with auto-detection)."""
    if not current_user.can_add_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Validate file type
    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    _, ext = os.path.splitext(file.filename.lower())
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type {ext} not allowed'}), 400

    # Validate file size (50MB max)
    file_data = file.read()
    if len(file_data) > 50 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File too large (max 50MB)'}), 413

    template_id = request.form.get('template_id')
    result = _service.parse_invoice(
        file_data, file.filename,
        template_id=int(template_id) if template_id else None,
    )
    if result.success:
        return jsonify({'success': True, 'data': result.data})
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/parse-existing/<path:filepath>')
@login_required
@handle_api_errors
def api_parse_existing(filepath):
    """Parse an existing invoice from the Invoices folder."""
    from core.config import INVOICES_DIR
    from accounting.bugetare.invoice_parser import parse_invoice
    file_path = os.path.realpath(os.path.join(INVOICES_DIR, filepath))

    # Prevent path traversal — resolved path must stay within INVOICES_DIR
    if not file_path.startswith(os.path.realpath(INVOICES_DIR) + os.sep):
        return jsonify({'success': False, 'error': 'Invalid file path'}), 400

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': 'File not found'}), 404

    result = parse_invoice(file_path)
    return jsonify({'success': True, 'data': result})


@invoices_bp.route('/api/suggest-department')
@login_required
@handle_api_errors
def api_suggest_department():
    """Suggest department based on historical allocations for the same supplier."""
    supplier = request.args.get('supplier', '').strip()
    if not supplier:
        return jsonify({'suggestions': []})

    rows = _invoice_repo.get_department_suggestions(supplier)
    suggestions = [
        {
            'company': r['company'],
            'brand': r['brand'],
            'department': r['department'],
            'subdepartment': r['subdepartment'],
            'frequency': r['frequency'],
        }
        for r in rows
    ]
    return jsonify({'suggestions': suggestions})


@invoices_bp.route('/api/invoices')
@login_required
def api_list_invoices():
    """List available invoices in the Invoices folder (including subfolders)."""
    from core.config import INVOICES_DIR
    if not os.path.exists(INVOICES_DIR):
        return jsonify([])

    files = []
    for root, dirs, filenames in os.walk(INVOICES_DIR):
        for f in filenames:
            if f.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                rel_path = os.path.relpath(os.path.join(root, f), INVOICES_DIR)
                files.append(rel_path)
    return jsonify(sorted(files))


# ============== INVOICE CRUD ==============

@invoices_bp.route('/api/db/invoices')
@login_required
def api_db_invoices():
    """Get all invoices from database with pagination and optional filters."""
    if not current_user.can_view_invoices:
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

    if include_allocations:
        invoices = _invoice_repo.get_all_with_allocations(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    else:
        invoices = _invoice_repo.get_all(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status
        )
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>')
@login_required
def api_db_invoice_detail(invoice_id):
    """Get invoice with all allocations."""
    if not current_user.can_view_invoices:
        return error_response('You do not have permission to view invoices', 403)

    invoice = _invoice_repo.get_with_allocations(invoice_id)
    if invoice:
        return jsonify(invoice)
    return error_response('Invoice not found', 404)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['DELETE'])
@login_required
def api_db_delete_invoice(invoice_id):
    """Soft delete an invoice (move to bin)."""
    if not current_user.can_delete_invoices:
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
    if not current_user.can_delete_invoices:
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
    if not current_user.can_delete_invoices:
        return jsonify({'success': False, 'error': 'You do not have permission to delete invoices'}), 403

    result = _service.permanently_delete(invoice_id, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@invoices_bp.route('/api/db/invoices/bulk-delete', methods=['POST'])
@login_required
def api_db_bulk_delete_invoices():
    """Soft delete multiple invoices."""
    if not current_user.can_delete_invoices:
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
    if not current_user.can_delete_invoices:
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
    if not current_user.can_delete_invoices:
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
    if not current_user.can_view_invoices:
        return error_response('You do not have permission to view invoices', 403)

    invoices = _invoice_repo.get_all(include_deleted=True, limit=500)
    return jsonify(invoices)


@invoices_bp.route('/api/db/invoices/<int:invoice_id>', methods=['PUT'])
@login_required
def api_db_update_invoice(invoice_id):
    """Update an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    result = _service.update_invoice(invoice_id, data, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ============== ALLOCATION ROUTES ==============

@invoices_bp.route('/api/db/invoices/<int:invoice_id>/allocations', methods=['PUT'])
@login_required
def api_db_update_allocations(invoice_id):
    """Update all allocations for an invoice."""
    if not current_user.can_edit_invoices:
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
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    comment = data.get('comment', '')

    updated = _allocation_repo.update_comment(allocation_id, comment)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Allocation not found'}), 404


@invoices_bp.route('/api/invoices/<int:invoice_id>/drive-link', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_invoice_drive_link(invoice_id):
    """Update only the drive_link for an invoice."""
    if not current_user.can_edit_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json()
    drive_link = data.get('drive_link')

    if not drive_link:
        return jsonify({'success': False, 'error': 'drive_link is required'}), 400

    updated = _invoice_repo.update(invoice_id=invoice_id, drive_link=drive_link)
    if updated:
        return jsonify({'success': True})
    return error_response('Invoice not found', 404)


# ============== SEARCH ==============

@invoices_bp.route('/api/db/search')
@login_required
def api_db_search():
    """Search invoices by supplier or invoice number, respecting active filters."""
    if not current_user.can_view_invoices:
        return error_response('You do not have permission to view invoices', 403)

    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    filters = {
        'company': request.args.get('company'),
        'department': request.args.get('department'),
        'subdepartment': request.args.get('subdepartment'),
        'brand': request.args.get('brand'),
        'status': request.args.get('status'),
        'payment_status': request.args.get('payment_status'),
        'start_date': request.args.get('start_date'),
        'end_date': request.args.get('end_date'),
    }
    filters = {k: v for k, v in filters.items() if v}

    results = _invoice_repo.search(query, filters)
    return jsonify(results)


@invoices_bp.route('/api/invoices/search')
@login_required
def api_invoices_search():
    """Search invoices by supplier, invoice number, or ID."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    query = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)

    if len(query) < 2:
        return jsonify({'success': True, 'invoices': [], 'message': 'Query too short'})

    if query.isdigit():
        invoice = _invoice_repo.get_with_allocations(int(query))
        if invoice:
            return jsonify({'success': True, 'invoices': [invoice]})

    results = _invoice_repo.search(query)[:limit]
    return jsonify({'success': True, 'invoices': results})


@invoices_bp.route('/api/db/check-invoice-number')
@login_required
def api_check_invoice_number():
    """Check if an invoice number already exists in the database."""
    invoice_number = request.args.get('invoice_number', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)

    if not invoice_number:
        return jsonify({'exists': False, 'invoice': None})

    result = _invoice_repo.check_number_exists(invoice_number, exclude_id)
    return jsonify(result)


# ============== SUMMARY ROUTES ==============

@invoices_bp.route('/api/db/summary/company')
@login_required
def api_db_summary_company():
    """Get summary grouped by company."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_company(start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/department')
@login_required
def api_db_summary_department():
    """Get summary grouped by department."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_department(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/brand')
@login_required
def api_db_summary_brand():
    """Get summary grouped by brand (Linie de business)."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_brand(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/supplier')
@login_required
def api_db_summary_supplier():
    """Get summary grouped by supplier."""
    if not current_user.can_view_invoices:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    summary = _summary_repo.by_supplier(company, start_date, end_date, department, subdepartment, brand)
    return jsonify(summary)
