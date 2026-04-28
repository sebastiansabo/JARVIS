"""Search and summary routes for invoices."""
from ._shared import *  # noqa: F401, F403


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
    org_filter = _get_org_filter_for_scope(scope)
    results = _invoice_repo.search(query, filters, responsible_user_id=responsible_user_id, org_filter=org_filter)
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
    org_filter = _get_org_filter_for_scope(scope)
    summary = _summary_repo.by_company(start_date, end_date, department, subdepartment, brand,
                                       responsible_user_id=responsible_user_id, org_filter=org_filter)
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
    org_filter = _get_org_filter_for_scope(scope)
    summary = _summary_repo.by_department(company, start_date, end_date, department, subdepartment, brand,
                                          responsible_user_id=responsible_user_id, org_filter=org_filter)
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
    org_filter = _get_org_filter_for_scope(scope)
    summary = _summary_repo.by_brand(company, start_date, end_date, department, subdepartment, brand,
                                     responsible_user_id=responsible_user_id, org_filter=org_filter)
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
    org_filter = _get_org_filter_for_scope(scope)
    summary = _summary_repo.by_supplier(company, start_date, end_date, department, subdepartment, brand,
                                        responsible_user_id=responsible_user_id, org_filter=org_filter)
    return jsonify(summary)
