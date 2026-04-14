"""Transaction routes (list, detail, update, bulk-ignore, bulk-status, summary, export,
link/unlink, auto-match, suggestions, accept/reject-match, merge/unmerge)."""
from ._shared import *  # noqa: F401, F403


# ============== TRANSACTIONS ==============

@statements_bp.route('/api/transactions', methods=['GET'])
@api_login_required
@statements_access_required
def list_transactions():
    """List transactions with optional filters."""
    transactions = statements_service.get_all_transactions(
        status=request.args.get('status'),
        company_cui=request.args.get('company_cui'),
        supplier=request.args.get('supplier'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        search=request.args.get('search'),
        sort=request.args.get('sort'),
        limit=int(request.args.get('limit', 500)),
        offset=int(request.args.get('offset', 0))
    )

    return jsonify({
        'success': True,
        'transactions': transactions,
        'count': len(transactions)
    })


@statements_bp.route('/api/transactions/<int:transaction_id>', methods=['GET'])
@api_login_required
@statements_access_required
def get_single_transaction(transaction_id):
    """Get a single transaction by ID."""
    txn = statements_service.get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    return jsonify({'success': True, 'transaction': txn})


@statements_bp.route('/api/transactions/<int:transaction_id>', methods=['PUT'])
@api_login_required
@statements_access_required
def update_single_transaction(transaction_id):
    """Update a transaction."""
    data, error = get_json_or_error()
    if error:
        return error

    # Validate status if provided
    if data.get('status') and data['status'] not in ('pending', 'resolved', 'ignored'):
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': {'status': 'Status must be one of: pending, resolved, ignored'}
        }), 422

    result = statements_service.update_transaction(
        transaction_id,
        matched_supplier=data.get('matched_supplier'),
        status=data.get('status'),
        vendor_name=data.get('vendor_name')
    )

    if result.success:
        return jsonify({'success': True})
    return jsonify({
        'success': False,
        'error': result.error
    }), 404


@statements_bp.route('/api/transactions/bulk-ignore', methods=['POST'])
@api_login_required
@statements_access_required
@rate_limit_bulk
def bulk_ignore_transactions():
    """Bulk ignore transactions."""
    data, error = get_json_or_error()
    if error:
        return error

    ids = data.get('transaction_ids', [])

    if not ids:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': {'transaction_ids': 'At least one transaction ID is required'}
        }), 400

    if not isinstance(ids, list):
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': {'transaction_ids': 'Must be an array of integers'}
        }), 422

    # Enforce item count limit
    if len(ids) > MAX_BULK_ITEMS:
        return jsonify({
            'success': False,
            'error': 'Too many items',
            'details': {
                'transaction_ids': f'Maximum {MAX_BULK_ITEMS} items per request',
                'received': len(ids),
                'max_allowed': MAX_BULK_ITEMS
            }
        }), 400

    result = statements_service.bulk_ignore_transactions(ids)
    return jsonify({
        'success': True,
        'updated_count': result.data['updated_count']
    })


@statements_bp.route('/api/transactions/bulk-status', methods=['POST'])
@api_login_required
@statements_access_required
@rate_limit_bulk
def bulk_update_transaction_status():
    """Bulk update status for transactions."""
    data, error = get_json_or_error()
    if error:
        return error

    ids = data.get('transaction_ids', [])
    status = data.get('status')

    # Validate fields
    errors = {}
    if not ids:
        errors['transaction_ids'] = 'At least one transaction ID is required'
    elif not isinstance(ids, list):
        errors['transaction_ids'] = 'Must be an array of integers'
    elif len(ids) > MAX_BULK_ITEMS:
        errors['transaction_ids'] = f'Maximum {MAX_BULK_ITEMS} items per request (received {len(ids)})'
    if not status:
        errors['status'] = 'Status is required'
    elif status not in ('pending', 'resolved', 'ignored'):
        errors['status'] = 'Status must be one of: pending, resolved, ignored'

    if errors:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': errors
        }), 422 if 'status' in errors and status else 400

    result = statements_service.bulk_update_status(ids, status)
    return jsonify({
        'success': True,
        'updated_count': result.data['updated_count']
    })


@statements_bp.route('/api/summary', methods=['GET'])
@api_login_required
@statements_access_required
def transactions_summary():
    """Get summary statistics for transactions."""
    summary = statements_service.get_transaction_summary(
        company_cui=request.args.get('company_cui'),
        supplier=request.args.get('supplier'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to')
    )
    return jsonify({
        'success': True,
        'summary': summary
    })


@statements_bp.route('/api/export/csv', methods=['GET'])
@api_login_required
@statements_access_required
def export_transactions_csv():
    """Export transactions to CSV format."""
    # Get transactions with same filters as list endpoint
    transactions = statements_service.get_all_transactions(
        status=request.args.get('status'),
        company_cui=request.args.get('company_cui'),
        supplier=request.args.get('supplier'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        limit=10000,  # Higher limit for export
        offset=0
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # Header row
    writer.writerow([
        'Date', 'Description', 'Amount', 'Currency',
        'Status', 'Matched Supplier', 'Company'
    ])

    # Data rows
    for txn in transactions:
        writer.writerow([
            str(txn.get('transaction_date', '')),
            txn.get('description', ''),
            txn.get('amount', ''),
            txn.get('currency', 'RON'),
            txn.get('status', ''),
            txn.get('matched_supplier', ''),
            txn.get('company_name', '')
        ])

    # Generate filename with today's date
    filename = f"transactions_{date.today().isoformat()}.csv"

    # Return CSV response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


# ============== INVOICE LINKING ==============

@statements_bp.route('/api/transactions/link-invoice', methods=['POST'])
@api_login_required
@statements_access_required
def link_invoice_to_transaction():
    """Link an existing invoice to a bank statement transaction."""
    data, error = get_json_or_error()
    if error:
        return error

    transaction_id = data.get('transaction_id')
    invoice_id = data.get('invoice_id')

    # Validate required fields
    errors = {}
    if not transaction_id:
        errors['transaction_id'] = 'Transaction ID is required'
    if not invoice_id:
        errors['invoice_id'] = 'Invoice ID is required'

    if errors:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': errors
        }), 400

    result = statements_service.link_invoice(transaction_id, invoice_id)

    if result.success:
        return jsonify({
            'success': True,
            **result.data
        })

    # Determine status code based on error
    status_code = 404
    if 'already linked' in (result.error or ''):
        status_code = 409
    elif result.data and result.data.get('existing_invoice_id'):
        status_code = 409

    return jsonify({
        'success': False,
        'error': result.error,
        'details': result.data if result.data else None
    }), status_code


@statements_bp.route('/api/transactions/<int:transaction_id>/unlink', methods=['POST'])
@api_login_required
@statements_access_required
def unlink_invoice_from_transaction(transaction_id):
    """Remove the invoice link from a transaction."""
    result = statements_service.unlink_invoice(transaction_id)

    if result.success:
        return jsonify({
            'success': True,
            **result.data
        })

    status_code = 404 if result.error == 'Transaction not found' else 400
    return jsonify({
        'success': False,
        'error': result.error
    }), status_code


# ============== AUTO-MATCH INVOICES ==============

@statements_bp.route('/api/transactions/auto-match', methods=['POST'])
@api_login_required
@statements_access_required
def auto_match_invoices():
    """Run automatic invoice matching on pending transactions."""
    data = request.get_json(silent=True) or {}
    transaction_ids = data.get('transaction_ids')
    use_ai = data.get('use_ai', True)
    min_confidence = data.get('min_confidence', 0.7)

    result = statements_service.auto_match_invoices(
        transaction_ids=transaction_ids,
        use_ai=use_ai,
        min_confidence=min_confidence
    )

    if result.success:
        return jsonify({
            'success': True,
            **result.data
        })
    return jsonify({
        'success': False,
        'error': result.error
    }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/suggestions', methods=['GET'])
@api_login_required
@statements_access_required
def get_invoice_suggestions(transaction_id):
    """Get invoice suggestions for a specific transaction."""
    result = statements_service.get_invoice_suggestions(transaction_id)

    if result.success:
        return jsonify({
            'success': True,
            **result.data
        })

    status_code = 404 if result.error == 'Transaction not found' else 500
    return jsonify({
        'success': False,
        'error': result.error
    }), status_code


@statements_bp.route('/api/transactions/<int:transaction_id>/accept-match', methods=['POST'])
@api_login_required
@statements_access_required
def accept_match(transaction_id):
    """Accept a suggested invoice match."""
    data = request.get_json(silent=True) or {}
    override_invoice_id = data.get('invoice_id')

    result = statements_service.accept_match(transaction_id, override_invoice_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({
        'success': False,
        'error': result.error
    }), 400


@statements_bp.route('/api/transactions/<int:transaction_id>/reject-match', methods=['POST'])
@api_login_required
@statements_access_required
def reject_match(transaction_id):
    """Reject a suggested invoice match."""
    result = statements_service.reject_match(transaction_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({
        'success': False,
        'error': result.error
    }), 400


# ============== TRANSACTION MERGING ==============

@statements_bp.route('/api/transactions/merge', methods=['POST'])
@api_login_required
@statements_access_required
def merge_transactions_route():
    """Merge multiple transactions into a single transaction."""
    data = request.get_json(silent=True) or {}
    transaction_ids = data.get('transaction_ids', [])

    if not transaction_ids or not isinstance(transaction_ids, list):
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': {'transaction_ids': 'Must provide an array of transaction IDs'}
        }), 400

    if len(transaction_ids) < 2:
        return jsonify({
            'success': False,
            'error': 'At least 2 transactions required for merging'
        }), 400

    result = statements_service.merge_transactions(transaction_ids)

    if result.success:
        return jsonify({
            'success': True,
            'merged_transaction': result.data
        })
    return jsonify({
        'success': False,
        'error': result.error
    }), 400


@statements_bp.route('/api/transactions/<int:transaction_id>/unmerge', methods=['POST'])
@api_login_required
@statements_access_required
def unmerge_transaction_route(transaction_id):
    """Unmerge a merged transaction, restoring the original transactions."""
    result = statements_service.unmerge_transaction(transaction_id)

    if result.success:
        return jsonify({
            'success': True,
            'restored_ids': result.data['restored_ids'],
            'restored_count': result.data['restored_count']
        })
    return jsonify({
        'success': False,
        'error': result.error
    }), 400


@statements_bp.route('/api/transactions/<int:transaction_id>/merged-sources', methods=['GET'])
@api_login_required
@statements_access_required
def get_merged_sources(transaction_id):
    """Get the original transactions that were merged into this transaction."""
    result = statements_service.get_merged_sources(transaction_id)

    if result.success:
        return jsonify({
            'success': True,
            'sources': result.data['sources']
        })
    return jsonify({
        'success': False,
        'error': result.error
    }), 404
