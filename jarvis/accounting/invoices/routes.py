"""Invoice, allocation, and summary API routes."""
import os
import logging
from flask import jsonify, request, redirect
from flask_login import login_required, current_user

from . import invoices_bp
from .repositories import InvoiceRepository, AllocationRepository, SummaryRepository, InvoiceDmsLinkRepository
from .services import InvoiceService
from .services.invoice_service import UserContext
from core.utils.api_helpers import error_response, safe_error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger('jarvis.invoices.routes')

_invoice_repo = InvoiceRepository()
_allocation_repo = AllocationRepository()
_summary_repo = SummaryRepository()
_service = InvoiceService()
_perm_repo = PermissionRepository()


_LEGACY_FLAG = {
    'view': 'can_view_invoices',
    'add': 'can_add_invoices',
    'edit': 'can_edit_invoices',
    'delete': 'can_delete_invoices',
}

def _check_invoice_perm(action: str) -> bool:
    """Check invoices.records.<action> V2 permission for current user.

    Falls back to legacy boolean flag when no explicit v2 entry exists,
    so local/dev environments without seeded role_permissions_v2 still work.
    """
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'invoices', 'records', action)
    if perm.get('has_explicit_entry'):
        return perm.get('has_permission', False)
    # No v2 entry — fall back to legacy boolean on current_user
    legacy = _LEGACY_FLAG.get(action)
    return bool(getattr(current_user, legacy, False)) if legacy else False


def _get_invoice_scope(action: str) -> str:
    """Return the V2 scope for invoices.records.<action> ('own', 'department', 'all').

    Falls back to 'all' when no explicit v2 entry exists (legacy behaviour).
    """
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return 'deny'
    perm = _perm_repo.check_permission_v2(role_id, 'invoices', 'records', action)
    if perm.get('has_explicit_entry'):
        return perm.get('scope', 'deny')
    return 'all'  # legacy roles without v2 entries see everything


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
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'You do not have permission to add invoices'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    result = _service.submit_invoice(data, _get_user_context())
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ============== BULK INVOICE UPLOAD ==============

@invoices_bp.route('/api/invoices/bulk-parse', methods=['POST'])
@login_required
def api_bulk_parse():
    """Parse multiple uploaded invoices using AI. Returns array of parse results."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400
    if len(files) > 20:
        return jsonify({'success': False, 'error': 'Maximum 20 files per batch'}), 400

    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    results = []
    for f in files:
        _, ext = os.path.splitext(f.filename.lower())
        if ext not in allowed_extensions:
            results.append({'filename': f.filename, 'success': False, 'error': f'File type {ext} not allowed'})
            continue
        file_data = f.read()
        if len(file_data) > 50 * 1024 * 1024:
            results.append({'filename': f.filename, 'success': False, 'error': 'File too large (max 50MB)'})
            continue
        result = _service.parse_invoice(file_data, f.filename)
        if result.success:
            inv_num = result.data.get('invoice_number', '')
            dup = _invoice_repo.check_number_exists(inv_num) if inv_num else {'exists': False}
            results.append({
                'filename': f.filename,
                'success': True,
                'data': result.data,
                'duplicate': dup.get('exists', False),
            })
        else:
            results.append({'filename': f.filename, 'success': False, 'error': result.error})

    return jsonify({'success': True, 'results': results})


@invoices_bp.route('/api/invoices/bulk-submit', methods=['POST'])
@login_required
def api_bulk_submit():
    """Submit multiple parsed invoices at once."""
    if not _check_invoice_perm('add'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    invoices = data.get('invoices', [])
    if not invoices:
        return jsonify({'success': False, 'error': 'No invoices provided'}), 400

    user_ctx = _get_user_context()
    results = []
    for inv in invoices:
        try:
            result = _service.submit_invoice(inv, user_ctx)
            if result.success:
                results.append({
                    'invoice_number': inv.get('invoice_number', ''),
                    'success': True,
                    'invoice_id': result.data.get('invoice_id'),
                })
            else:
                results.append({
                    'invoice_number': inv.get('invoice_number', ''),
                    'success': False,
                    'error': result.error,
                })
        except Exception as e:
            results.append({
                'invoice_number': inv.get('invoice_number', ''),
                'success': False,
                'error': str(e),
            })

    saved = sum(1 for r in results if r['success'])
    return jsonify({
        'success': True,
        'results': results,
        'saved_count': saved,
        'total': len(invoices),
    })


# ============== INVOICE PARSING ==============

@invoices_bp.route('/api/parse-invoice', methods=['POST'])
@login_required
def api_parse_invoice():
    """Parse an uploaded invoice using AI or template (with auto-detection)."""
    if not _check_invoice_perm('add'):
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

    # Scope-based filtering: 'own' = only invoices where user is responsible
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None

    if include_allocations:
        invoices = _invoice_repo.get_all_with_allocations(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status,
            responsible_user_id=responsible_user_id
        )
    else:
        invoices = _invoice_repo.get_all(
            limit=limit, offset=offset, company=company,
            start_date=start_date, end_date=end_date,
            department=department, subdepartment=subdepartment, brand=brand,
            status=status, payment_status=payment_status,
            responsible_user_id=responsible_user_id
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

    # Scope check: 'own' users can only view invoices they're responsible for
    scope = _get_invoice_scope('view')
    if scope == 'own':
        allocations = invoice.get('allocations', [])
        user_ids = {a.get('responsible_user_id') for a in allocations if a}
        if current_user.id not in user_ids:
            return error_response('Invoice not found', 404)

    return jsonify(invoice)


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

    # Scope check: 'own' users can only edit their own invoices
    scope = _get_invoice_scope('edit')
    if scope == 'own':
        row = _invoice_repo.query_one(
            'SELECT 1 FROM allocations WHERE invoice_id = %s AND responsible_user_id = %s LIMIT 1',
            (invoice_id, current_user.id)
        )
        if not row:
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
    if not _check_invoice_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    # Scope check: 'own' users can only edit allocations on their own invoices
    scope = _get_invoice_scope('edit')
    if scope == 'own':
        row = _invoice_repo.query_one(
            'SELECT 1 FROM allocations WHERE invoice_id = %s AND responsible_user_id = %s LIMIT 1',
            (invoice_id, current_user.id)
        )
        if not row:
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


# ============== SEARCH ==============

@invoices_bp.route('/api/db/search')
@login_required
def api_db_search():
    """Search invoices by supplier or invoice number, respecting active filters."""
    if not _check_invoice_perm('view'):
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

    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    results = _invoice_repo.search(query, filters, responsible_user_id=responsible_user_id)
    return jsonify(results)


@invoices_bp.route('/api/invoices/search')
@login_required
def api_invoices_search():
    """Search invoices by supplier, invoice number, or ID."""
    if not _check_invoice_perm('view'):
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
    if not _check_invoice_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    summary = _summary_repo.by_company(start_date, end_date, department, subdepartment, brand,
                                       responsible_user_id=responsible_user_id)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/department')
@login_required
def api_db_summary_department():
    """Get summary grouped by department."""
    if not _check_invoice_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    summary = _summary_repo.by_department(company, start_date, end_date, department, subdepartment, brand,
                                          responsible_user_id=responsible_user_id)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/brand')
@login_required
def api_db_summary_brand():
    """Get summary grouped by brand (Linie de business)."""
    if not _check_invoice_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    summary = _summary_repo.by_brand(company, start_date, end_date, department, subdepartment, brand,
                                     responsible_user_id=responsible_user_id)
    return jsonify(summary)


@invoices_bp.route('/api/db/summary/supplier')
@login_required
def api_db_summary_supplier():
    """Get summary grouped by supplier."""
    if not _check_invoice_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    company = request.args.get('company')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    scope = _get_invoice_scope('view')
    responsible_user_id = current_user.id if scope == 'own' else None
    summary = _summary_repo.by_supplier(company, start_date, end_date, department, subdepartment, brand,
                                        responsible_user_id=responsible_user_id)
    return jsonify(summary)


# ============== STORE TO DMS ==============

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

    from core.base_repository import BaseRepository
    from dms.repositories import DocumentRepository, CategoryRepository
    from dms.services.folder_sync_service import FolderSyncService
    from core.tags.repositories.tag_repository import TagRepository

    base_repo = BaseRepository()
    doc_repo = DocumentRepository()
    cat_repo = CategoryRepository()
    folder_sync = FolderSyncService()
    tag_repo = TagRepository()
    dms_link_repo = InvoiceDmsLinkRepository()

    # Find "Facturi" category
    facturi_cat = base_repo.query_one(
        "SELECT id, name, icon, color FROM dms_categories WHERE slug = 'facturi' AND is_active = TRUE"
    )
    if not facturi_cat:
        facturi_cat = base_repo.query_one(
            "SELECT id, name, icon, color FROM dms_categories WHERE name ILIKE 'facturi' AND is_active = TRUE"
        )
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
            existing = base_repo.query_one('''
                SELECT l.document_id FROM invoice_dms_links l
                JOIN dms_documents d ON d.id = l.document_id
                WHERE l.invoice_id = %s AND d.deleted_at IS NULL
                  AND d.metadata->>'source' = 'store_to_dms'
            ''', (inv_id,))
            if existing:
                skipped.append({'id': inv_id, 'reason': 'already_stored', 'document_id': existing['document_id']})
                continue

            # Resolve company from allocations or fallback to current user
            company_name = None
            if inv.get('allocations'):
                company_name = inv['allocations'][0].get('company')

            company_id = None
            if company_name:
                comp_row = base_repo.query_one(
                    'SELECT id FROM companies WHERE company = %s', (company_name,))
                if comp_row:
                    company_id = comp_row['id']

            if not company_id:
                company_id = current_user.company_id

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
                parent_path = base_repo.query_one(
                    'SELECT path, depth FROM dms_folders WHERE id = %s', (folder_id,)
                )
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
                base_repo.execute(
                    'UPDATE dms_documents SET folder_id = %s WHERE id = %s',
                    (target_folder_id, doc['id'])
                )

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
