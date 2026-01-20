"""API routes for Bank Statement module."""
import re
import logging
import time
import hashlib
from collections import defaultdict
from functools import wraps
from flask import request, jsonify, render_template, Response
from flask_login import login_required, current_user

from . import statements_bp


def api_login_required(f):
    """Like @login_required but returns JSON 401 for API endpoints instead of redirecting."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'details': {'message': 'Please log in to access this resource'}
            }), 401
        return f(*args, **kwargs)
    return decorated_function

# File size limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB total per request

# Rate limiting constants
MAX_BULK_ITEMS = 100  # Max items per bulk request
RATE_LIMIT_REQUESTS = 10  # Max bulk requests per window
RATE_LIMIT_WINDOW = 60  # Window in seconds (1 minute)


class RateLimiter:
    """Simple in-memory rate limiter for bulk operations."""

    def __init__(self):
        # Dict of user_id -> list of request timestamps
        self._requests = defaultdict(list)

    def is_allowed(self, user_id: int, max_requests: int = RATE_LIMIT_REQUESTS,
                   window_seconds: int = RATE_LIMIT_WINDOW) -> tuple[bool, int]:
        """
        Check if a request is allowed for this user.

        Returns:
            (is_allowed, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old requests outside the window
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > window_start
        ]

        if len(self._requests[user_id]) >= max_requests:
            # Calculate retry-after
            oldest_in_window = min(self._requests[user_id])
            retry_after = int(oldest_in_window + window_seconds - now) + 1
            return False, max(1, retry_after)

        # Record this request
        self._requests[user_id].append(now)
        return True, 0

    def get_remaining(self, user_id: int, max_requests: int = RATE_LIMIT_REQUESTS,
                      window_seconds: int = RATE_LIMIT_WINDOW) -> int:
        """Get remaining requests for this user in the current window."""
        now = time.time()
        window_start = now - window_seconds

        # Count requests in window
        recent = [ts for ts in self._requests[user_id] if ts > window_start]
        return max(0, max_requests - len(recent))


# Global rate limiter instance
bulk_rate_limiter = RateLimiter()


def rate_limit_bulk(f):
    """Decorator to apply rate limiting to bulk operations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = current_user.id if current_user.is_authenticated else 0

        is_allowed, retry_after = bulk_rate_limiter.is_allowed(user_id)

        if not is_allowed:
            response = jsonify({
                'success': False,
                'error': 'Rate limit exceeded',
                'details': {
                    'message': f'Too many bulk requests. Maximum {RATE_LIMIT_REQUESTS} requests per minute.',
                    'retry_after': retry_after
                }
            })
            response.status_code = 429
            response.headers['Retry-After'] = str(retry_after)
            return response

        return f(*args, **kwargs)
    return decorated_function


def validate_regex(pattern: str) -> tuple[bool, str]:
    """Validate a regex pattern. Returns (is_valid, error_message)."""
    try:
        re.compile(pattern)
        return True, None
    except re.error as e:
        return False, str(e)


def get_json_or_error():
    """Get JSON from request with null check. Returns (data, error_response)."""
    data = request.get_json()
    if data is None:
        return None, jsonify({
            'success': False,
            'error': 'Invalid or missing JSON body',
            'details': {'body': 'Request body must be valid JSON'}
        }), 400
    return data, None
from .parser import parse_statement
from .vendors import match_transactions, reload_patterns, get_unmatched_vendors
from .database import (
    get_all_vendor_mappings,
    get_vendor_mapping,
    create_vendor_mapping,
    update_vendor_mapping,
    delete_vendor_mapping,
    seed_vendor_mappings,
    save_transactions_with_dedup,
    get_transactions,
    get_transaction,
    update_transaction,
    bulk_update_status,
    get_transaction_summary,
    # Statement management
    create_statement,
    get_statement,
    get_statements,
    get_statement_count,
    check_duplicate_statement,
    update_statement,
    delete_statement,
    # Filter options
    get_distinct_companies,
    get_distinct_suppliers,
    # Transaction merging
    merge_transactions,
    unmerge_transaction,
    get_merged_source_transactions
)

logger = logging.getLogger('jarvis.statements.routes')


# ============== PAGE ROUTES ==============

@statements_bp.route('/')
@login_required
def index():
    """Bank statement upload and review page."""
    return render_template('index.html')


@statements_bp.route('/mappings')
@login_required
def mappings_page():
    """Vendor mappings management page."""
    return render_template('mappings.html')


@statements_bp.route('/files')
@login_required
def files_page():
    """Statement files management page."""
    return render_template('files.html')


# ============== UPLOAD & PARSE ==============

@statements_bp.route('/api/upload', methods=['POST'])
@api_login_required
def upload_statements():
    """
    Upload and parse bank statement PDF(s).

    Accepts multipart/form-data with file(s) under 'files' key.

    Returns:
        {
            'success': bool,
            'statements': [{
                'filename': str,
                'statement_id': int,
                'company_name': str,
                'company_cui': str,
                'total_transactions': int,
                'new_transactions': int,
                'duplicate_transactions': int,
                'matched_count': int,
                'period': {from, to}
            }],
            'total_new': int,
            'total_duplicates': int
        }
    """
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    # Validate file sizes
    total_size = 0
    for file in files:
        if not file.filename:
            continue
        # Get file size by seeking to end
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                'success': False,
                'error': f'File {file.filename} exceeds maximum size of 10MB'
            }), 400

        total_size += file_size

    if total_size > MAX_TOTAL_SIZE:
        return jsonify({
            'success': False,
            'error': f'Total upload size exceeds maximum of 50MB'
        }), 400

    # Ensure vendor mappings are seeded
    seed_vendor_mappings()

    results = []
    total_new = 0
    total_duplicates = 0

    for file in files:
        if not file.filename:
            continue

        if not file.filename.lower().endswith('.pdf'):
            logger.warning(f'Skipping non-PDF file: {file.filename}')
            continue

        try:
            pdf_bytes = file.read()

            # Calculate file hash for duplicate detection
            file_hash = hashlib.md5(pdf_bytes).hexdigest()

            # Check if this exact file was already uploaded
            existing = check_duplicate_statement(file_hash)
            if existing:
                results.append({
                    'filename': file.filename,
                    'error': f'This file was already uploaded on {existing["uploaded_at"]}',
                    'existing_statement_id': existing['id'],
                    'skipped': True
                })
                continue

            # Parse the statement
            parsed = parse_statement(pdf_bytes, file.filename)

            # Match transactions to vendors
            transactions = match_transactions(parsed['transactions'])

            # Create statement record first
            period = parsed.get('period', {})
            statement_id = create_statement(
                filename=file.filename,
                file_hash=file_hash,
                company_name=parsed.get('company_name'),
                company_cui=parsed.get('company_cui'),
                account_number=parsed.get('account_number'),
                period_from=period.get('from'),
                period_to=period.get('to'),
                total_transactions=len(transactions),
                uploaded_by=current_user.id if current_user.is_authenticated else None
            )

            # Save transactions with duplicate detection
            save_result = save_transactions_with_dedup(transactions, statement_id)

            # Update statement with actual counts
            update_statement(
                statement_id,
                new_transactions=save_result['new_count'],
                duplicate_transactions=save_result['duplicate_count']
            )

            # Auto-match new transactions to invoices
            invoice_matched_count = 0
            if save_result['new_ids']:
                try:
                    from .invoice_matcher import auto_match_transactions
                    from .database import get_candidate_invoices, bulk_update_transaction_matches

                    # Get the newly saved transactions for matching
                    new_txns = [get_transaction(txn_id) for txn_id in save_result['new_ids']]
                    new_txns = [t for t in new_txns if t and t.get('status') not in ('ignored',)]

                    if new_txns:
                        # Get candidate invoices
                        invoices = get_candidate_invoices(limit=200)
                        if invoices:
                            # Run auto-match
                            match_results = auto_match_transactions(
                                transactions=new_txns,
                                invoices=invoices,
                                use_ai=False,
                                min_confidence=0.5
                            )
                            # Save match results
                            if match_results['results']:
                                bulk_update_transaction_matches(match_results['results'])
                            invoice_matched_count = match_results.get('matched', 0) + match_results.get('suggested', 0)
                            logger.info(f'Auto-matched {invoice_matched_count} transactions to invoices')
                except Exception as e:
                    logger.warning(f'Auto-match failed: {e}')

            # Count vendor-matched (has supplier) - just for reporting
            vendor_matched_count = sum(1 for t in transactions if t.get('matched_supplier'))

            total_new += save_result['new_count']
            total_duplicates += save_result['duplicate_count']

            results.append({
                'filename': file.filename,
                'statement_id': statement_id,
                'company_name': parsed.get('company_name'),
                'company_cui': parsed.get('company_cui'),
                'total_transactions': len(transactions),
                'new_transactions': save_result['new_count'],
                'duplicate_transactions': save_result['duplicate_count'],
                'vendor_matched_count': vendor_matched_count,
                'invoice_matched_count': invoice_matched_count,
                'period': period,
                'summary': parsed.get('summary')
            })

        except Exception as e:
            logger.exception(f'Error parsing {file.filename}')
            results.append({
                'filename': file.filename,
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'statements': results,
        'total_new': total_new,
        'total_duplicates': total_duplicates
    })


# ============== STATEMENT MANAGEMENT ==============

@statements_bp.route('/api/statements', methods=['GET'])
@api_login_required
def list_statements():
    """
    List all uploaded statements with pagination.

    Query params:
        - limit: max results (default 100)
        - offset: pagination offset
    """
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    statements = get_statements(limit=limit, offset=offset)
    total = get_statement_count()

    # Convert dates to strings for JSON
    for stmt in statements:
        if stmt.get('period_from'):
            stmt['period_from'] = str(stmt['period_from'])
        if stmt.get('period_to'):
            stmt['period_to'] = str(stmt['period_to'])
        if stmt.get('uploaded_at'):
            stmt['uploaded_at'] = str(stmt['uploaded_at'])

    return jsonify({
        'success': True,
        'statements': statements,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@statements_bp.route('/api/statements/<int:statement_id>', methods=['GET'])
@api_login_required
def get_statement_detail(statement_id):
    """Get details for a single statement."""
    stmt = get_statement(statement_id)
    if not stmt:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404

    # Convert dates to strings
    if stmt.get('period_from'):
        stmt['period_from'] = str(stmt['period_from'])
    if stmt.get('period_to'):
        stmt['period_to'] = str(stmt['period_to'])
    if stmt.get('uploaded_at'):
        stmt['uploaded_at'] = str(stmt['uploaded_at'])

    return jsonify({'success': True, 'statement': stmt})


@statements_bp.route('/api/statements/<int:statement_id>', methods=['DELETE'])
@api_login_required
def delete_statement_route(statement_id):
    """Delete a statement and all its transactions."""
    stmt = get_statement(statement_id)
    if not stmt:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404

    success = delete_statement(statement_id)
    if success:
        logger.info(f'Deleted statement {statement_id}: {stmt["filename"]}')
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to delete statement'}), 500


# ============== FILTER OPTIONS ==============

@statements_bp.route('/api/filters', methods=['GET'])
@api_login_required
def get_filter_options():
    """
    Get available filter options for dropdowns.

    Returns:
        {
            'companies': [{'company_name': str, 'company_cui': str}, ...],
            'suppliers': [str, ...]
        }
    """
    companies = get_distinct_companies()
    suppliers = get_distinct_suppliers()

    return jsonify({
        'success': True,
        'companies': companies,
        'suppliers': suppliers
    })


# ============== TRANSACTIONS ==============

@statements_bp.route('/api/transactions', methods=['GET'])
@api_login_required
def list_transactions():
    """
    List transactions with optional filters.

    Query params:
        - status: pending, matched, ignored, invoiced
        - company_cui: filter by company
        - supplier: filter by matched supplier
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
        - limit: max results (default 500)
        - offset: pagination offset
    """
    transactions = get_transactions(
        status=request.args.get('status'),
        company_cui=request.args.get('company_cui'),
        supplier=request.args.get('supplier'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        limit=int(request.args.get('limit', 500)),
        offset=int(request.args.get('offset', 0))
    )

    # Convert dates to ISO strings for JSON
    for txn in transactions:
        if txn.get('transaction_date'):
            txn['transaction_date'] = str(txn['transaction_date'])
        if txn.get('value_date'):
            txn['value_date'] = str(txn['value_date'])
        if txn.get('created_at'):
            txn['created_at'] = str(txn['created_at'])
        # Convert linked invoice date from JOIN
        if txn.get('linked_invoice_date'):
            txn['linked_invoice_date'] = str(txn['linked_invoice_date'])
        # Convert suggested invoice date from JOIN
        if txn.get('suggested_invoice_date'):
            txn['suggested_invoice_date'] = str(txn['suggested_invoice_date'])

    return jsonify({
        'success': True,
        'transactions': transactions,
        'count': len(transactions)
    })


@statements_bp.route('/api/transactions/<int:transaction_id>', methods=['GET'])
@api_login_required
def get_single_transaction(transaction_id):
    """Get a single transaction by ID."""
    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    # Convert dates
    if txn.get('transaction_date'):
        txn['transaction_date'] = str(txn['transaction_date'])
    if txn.get('value_date'):
        txn['value_date'] = str(txn['value_date'])

    return jsonify({'success': True, 'transaction': txn})


@statements_bp.route('/api/transactions/<int:transaction_id>', methods=['PUT'])
@api_login_required
def update_single_transaction(transaction_id):
    """
    Update a transaction.

    Body can include: matched_supplier, status, vendor_name
    """
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

    try:
        success = update_transaction(
            transaction_id,
            matched_supplier=data.get('matched_supplier'),
            status=data.get('status'),
            vendor_name=data.get('vendor_name')
        )

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': 'Transaction not found or no changes made'
            }), 404
    except Exception as e:
        logger.exception(f"Failed to update transaction {transaction_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/transactions/bulk-ignore', methods=['POST'])
@api_login_required
@rate_limit_bulk
def bulk_ignore_transactions():
    """
    Bulk ignore transactions.

    Body: { "transaction_ids": [1, 2, 3] }

    Rate limited: 10 requests per minute, max 100 items per request.
    """
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

    try:
        count = bulk_update_status(ids, 'ignored')
        return jsonify({
            'success': True,
            'updated_count': count
        })
    except Exception as e:
        logger.exception(f"Failed to bulk ignore transactions: {e}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/transactions/bulk-status', methods=['POST'])
@api_login_required
@rate_limit_bulk
def bulk_update_transaction_status():
    """
    Bulk update status for transactions.

    Body: { "transaction_ids": [1, 2, 3], "status": "resolved" }

    Rate limited: 10 requests per minute, max 100 items per request.
    """
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

    try:
        count = bulk_update_status(ids, status)
        return jsonify({
            'success': True,
            'updated_count': count
        })
    except Exception as e:
        logger.exception(f"Failed to bulk update status: {e}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/summary', methods=['GET'])
@api_login_required
def transactions_summary():
    """Get summary statistics for transactions.

    Query params (for cascading filters):
        - company_cui: Filter suppliers by company
        - supplier: Filter companies by supplier
        - date_from: Filter by date range start
        - date_to: Filter by date range end
    """
    summary = get_transaction_summary(
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
def export_transactions_csv():
    """
    Export transactions to CSV format.

    Query params (same as list_transactions):
        - status: pending, matched, ignored, invoiced
        - company_cui: filter by company
        - supplier: filter by matched supplier
        - date_from: YYYY-MM-DD
        - date_to: YYYY-MM-DD
    """
    import csv
    import io
    from datetime import date

    # Get transactions with same filters as list endpoint
    transactions = get_transactions(
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


# ============== VENDOR MAPPINGS ==============

@statements_bp.route('/api/mappings', methods=['GET'])
@api_login_required
def list_mappings():
    """List all vendor mappings."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    mappings = get_all_vendor_mappings(active_only=active_only)

    return jsonify({
        'success': True,
        'mappings': mappings
    })


@statements_bp.route('/api/mappings', methods=['POST'])
@api_login_required
def create_mapping():
    """
    Create a new vendor mapping.

    Body: {
        "pattern": "VENDOR\\s*\\*",
        "supplier_name": "Vendor Inc",
        "supplier_vat": "RO12345678" (optional),
        "template_id": 1 (optional)
    }
    """
    data, error = get_json_or_error()
    if error:
        return error

    # Validate required fields
    errors = {}
    if not data.get('pattern'):
        errors['pattern'] = 'Pattern is required'
    if not data.get('supplier_name'):
        errors['supplier_name'] = 'Supplier name is required'

    if errors:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': errors
        }), 400

    # Validate regex pattern
    is_valid, regex_error = validate_regex(data['pattern'])
    if not is_valid:
        logger.warning(f"Invalid regex pattern: {data['pattern']} - {regex_error}")
        return jsonify({
            'success': False,
            'error': 'Invalid regex pattern',
            'details': {'pattern': regex_error}
        }), 422

    try:
        mapping_id = create_vendor_mapping(
            pattern=data['pattern'],
            supplier_name=data['supplier_name'],
            supplier_vat=data.get('supplier_vat'),
            template_id=data.get('template_id')
        )

        # Reload patterns cache
        reload_patterns()

        return jsonify({
            'success': True,
            'mapping_id': mapping_id
        })
    except Exception as e:
        logger.exception(f"Failed to create mapping: {e}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['GET'])
@api_login_required
def get_single_mapping(mapping_id):
    """Get a single vendor mapping by ID."""
    mapping = get_vendor_mapping(mapping_id)
    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    return jsonify({'success': True, 'mapping': mapping})


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
@api_login_required
def update_single_mapping(mapping_id):
    """
    Update a vendor mapping.

    Body can include: pattern, supplier_name, supplier_vat, template_id, is_active
    """
    data, error = get_json_or_error()
    if error:
        return error

    # Validate regex pattern if provided
    if data.get('pattern'):
        is_valid, regex_error = validate_regex(data['pattern'])
        if not is_valid:
            logger.warning(f"Invalid regex pattern for mapping {mapping_id}: {data['pattern']} - {regex_error}")
            return jsonify({
                'success': False,
                'error': 'Invalid regex pattern',
                'details': {'pattern': regex_error}
            }), 422

    try:
        success = update_vendor_mapping(
            mapping_id,
            pattern=data.get('pattern'),
            supplier_name=data.get('supplier_name'),
            supplier_vat=data.get('supplier_vat'),
            template_id=data.get('template_id'),
            is_active=data.get('is_active')
        )

        if success:
            # Reload patterns cache
            reload_patterns()
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': 'Mapping not found or no changes made'
            }), 404
    except Exception as e:
        logger.exception(f"Failed to update mapping {mapping_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
@api_login_required
def delete_single_mapping(mapping_id):
    """Delete a vendor mapping."""
    success = delete_vendor_mapping(mapping_id)

    if success:
        # Reload patterns cache
        reload_patterns()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Delete failed'}), 400


# ============== INVOICE LINKING ==============

@statements_bp.route('/api/transactions/link-invoice', methods=['POST'])
@api_login_required
def link_invoice_to_transaction():
    """
    Link an existing invoice to a bank statement transaction.

    Body: {
        "transaction_id": 123,
        "invoice_id": 456
    }

    This marks the transaction as 'resolved' and stores the invoice_id reference.
    """
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

    # Verify transaction exists
    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({
            'success': False,
            'error': 'Transaction not found'
        }), 404

    # Check if already linked
    if txn.get('invoice_id'):
        return jsonify({
            'success': False,
            'error': 'Transaction is already linked to an invoice',
            'details': {'existing_invoice_id': txn['invoice_id']}
        }), 409

    # Verify invoice exists (import here to avoid circular imports)
    from database import get_invoice_with_allocations
    invoice = get_invoice_with_allocations(invoice_id)
    if not invoice:
        return jsonify({
            'success': False,
            'error': 'Invoice not found'
        }), 404

    try:
        # Update transaction with invoice link and set status to resolved
        success = update_transaction(
            transaction_id,
            invoice_id=invoice_id,
            status='resolved'
        )

        if success:
            logger.info(f'Linked transaction {transaction_id} to invoice {invoice_id}')
            return jsonify({
                'success': True,
                'transaction_id': transaction_id,
                'invoice_id': invoice_id
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update transaction'
            }), 500

    except Exception as e:
        logger.exception(f'Error linking transaction {transaction_id} to invoice {invoice_id}')
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/unlink', methods=['POST'])
@api_login_required
def unlink_invoice_from_transaction(transaction_id):
    """
    Remove the invoice link from a transaction.

    This sets the invoice_id to NULL and changes status back to 'pending'.
    """
    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({
            'success': False,
            'error': 'Transaction not found'
        }), 404

    if not txn.get('invoice_id'):
        return jsonify({
            'success': False,
            'error': 'Transaction is not linked to any invoice'
        }), 400

    try:
        # Set status back to pending when unlinking
        new_status = 'pending'

        success = update_transaction(
            transaction_id,
            invoice_id=None,
            status=new_status
        )

        if success:
            logger.info(f'Unlinked invoice from transaction {transaction_id}')
            return jsonify({
                'success': True,
                'transaction_id': transaction_id,
                'new_status': new_status
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update transaction'
            }), 500

    except Exception as e:
        logger.exception(f'Error unlinking invoice from transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': 'Database error',
            'details': {'message': str(e)}
        }), 500


# ============== AUTO-MATCH INVOICES ==============

@statements_bp.route('/api/transactions/auto-match', methods=['POST'])
@api_login_required
def auto_match_invoices():
    """
    Run automatic invoice matching on pending transactions.

    Body (all optional):
    {
        "transaction_ids": [1, 2, 3],  // Specific transactions to match
        "use_ai": true,                 // Enable AI fallback (default true)
        "min_confidence": 0.7           // Minimum confidence for suggestions
    }

    Returns:
    {
        "success": true,
        "matched": 5,       // Auto-accepted matches
        "suggested": 3,     // Suggestions for review
        "unmatched": 2,     // No match found
        "results": [...]    // Detailed results
    }
    """
    from .invoice_matcher import auto_match_transactions
    from .database import (
        get_transactions_for_matching,
        get_candidate_invoices,
        bulk_update_transaction_matches
    )

    data = request.get_json(silent=True) or {}
    transaction_ids = data.get('transaction_ids')
    use_ai = data.get('use_ai', True)
    min_confidence = data.get('min_confidence', 0.7)

    try:
        # Get transactions to match
        if transaction_ids:
            # Get specific transactions
            transactions = []
            for txn_id in transaction_ids:
                txn = get_transaction(txn_id)
                if txn and txn.get('status') not in ('resolved', 'ignored'):
                    transactions.append(txn)
        else:
            # Get all pending transactions
            transactions = get_transactions_for_matching(status='pending', limit=100)

        if not transactions:
            return jsonify({
                'success': True,
                'matched': 0,
                'suggested': 0,
                'unmatched': 0,
                'results': [],
                'message': 'No transactions to match'
            })

        # Get candidate invoices (recent, unpaid, not deleted)
        invoices = get_candidate_invoices(limit=200)

        if not invoices:
            return jsonify({
                'success': True,
                'matched': 0,
                'suggested': 0,
                'unmatched': len(transactions),
                'results': [],
                'message': 'No invoices available for matching'
            })

        # Run the matching algorithm
        match_results = auto_match_transactions(
            transactions=transactions,
            invoices=invoices,
            use_ai=use_ai,
            min_confidence=min_confidence
        )

        # Save results to database
        if match_results['results']:
            bulk_update_transaction_matches(match_results['results'])

        return jsonify({
            'success': True,
            'matched': match_results['matched'],
            'suggested': match_results['suggested'],
            'unmatched': match_results['unmatched'],
            'results': match_results['results']
        })

    except Exception as e:
        logger.exception('Error in auto-match')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/suggestions', methods=['GET'])
@api_login_required
def get_invoice_suggestions(transaction_id):
    """
    Get invoice suggestions for a specific transaction.

    Returns top candidates with scores and reasons.
    """
    from .invoice_matcher import score_candidates
    from .database import get_candidate_invoices

    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    try:
        # Get candidate invoices - use broad filter to show more options
        amount = abs(txn.get('amount', 0))
        currency = txn.get('currency', 'RON')

        # Get broad candidate set (don't filter by supplier to show more options)
        invoices = get_candidate_invoices(
            supplier=None,
            amount=amount,
            amount_tolerance=0.2,  # 20% tolerance for suggestions
            currency=currency,
            limit=50
        )

        # Score candidates
        candidates = score_candidates(txn, invoices, limit=5)

        # Format for response
        suggestions = []
        for c in candidates:
            inv = c['invoice']
            suggestions.append({
                'invoice_id': inv.get('id'),
                'invoice_number': inv.get('invoice_number'),
                'supplier': inv.get('supplier'),
                'amount': inv.get('invoice_value'),
                'currency': inv.get('currency'),
                'date': inv.get('invoice_date'),
                'score': c['score'],
                'confidence': c['confidence'],
                'reasons': c['reasons']
            })

        return jsonify({
            'success': True,
            'transaction': {
                'id': txn.get('id'),
                'amount': txn.get('amount'),
                'currency': txn.get('currency'),
                'date': str(txn.get('transaction_date')) if txn.get('transaction_date') else None,
                'vendor': txn.get('vendor_name'),
                'supplier': txn.get('matched_supplier'),
                'description': txn.get('description')
            },
            'suggestions': suggestions
        })

    except Exception as e:
        logger.exception(f'Error getting suggestions for transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/accept-match', methods=['POST'])
@api_login_required
def accept_match(transaction_id):
    """
    Accept a suggested invoice match.

    Body (optional):
    {
        "invoice_id": 123  // Override suggested invoice
    }
    """
    from .database import accept_suggested_match, update_transaction_match

    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    data = request.get_json(silent=True) or {}
    override_invoice_id = data.get('invoice_id')

    try:
        if override_invoice_id:
            # Manual override - link to specified invoice
            success = update_transaction_match(
                transaction_id,
                invoice_id=override_invoice_id,
                match_method='manual',
                status='resolved'
            )
        else:
            # Accept the existing suggestion
            success = accept_suggested_match(transaction_id)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': 'No suggestion to accept or update failed'
            }), 400

    except Exception as e:
        logger.exception(f'Error accepting match for transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/reject-match', methods=['POST'])
@api_login_required
def reject_match(transaction_id):
    """
    Reject a suggested invoice match.
    """
    from .database import reject_suggested_match

    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    try:
        success = reject_suggested_match(transaction_id)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'error': 'No suggestion to reject'
            }), 400

    except Exception as e:
        logger.exception(f'Error rejecting match for transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============== TRANSACTION MERGING ==============

@statements_bp.route('/api/transactions/merge', methods=['POST'])
@api_login_required
def merge_transactions_route():
    """
    Merge multiple transactions into a single transaction.

    Body: {
        "transaction_ids": [1, 2, 3]  // At least 2 transaction IDs
    }

    Requirements:
    - All transactions must be pending (not already merged/resolved/ignored)
    - All transactions must have the same currency
    - All transactions must have the same supplier

    Returns:
    {
        "success": true,
        "merged_transaction": {
            "id": 123,
            "amount": 500.00,
            "currency": "RON",
            "transaction_date": "2025-01-15",
            "description": "...",
            "merged_count": 3,
            "merged_from_ids": [1, 2, 3]
        }
    }
    """
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

    try:
        result = merge_transactions(transaction_ids)

        if result.get('error'):
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400

        logger.info(f'Merged transactions {transaction_ids} into {result["id"]}')
        return jsonify({
            'success': True,
            'merged_transaction': result
        })

    except Exception as e:
        logger.exception(f'Error merging transactions {transaction_ids}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/unmerge', methods=['POST'])
@api_login_required
def unmerge_transaction_route(transaction_id):
    """
    Unmerge a merged transaction, restoring the original transactions.

    The merged transaction is deleted and original transactions are restored to 'pending' status.

    Returns:
    {
        "success": true,
        "restored_ids": [1, 2, 3],
        "restored_count": 3
    }
    """
    try:
        result = unmerge_transaction(transaction_id)

        if result.get('error'):
            return jsonify({
                'success': False,
                'error': result['error']
            }), 400

        logger.info(f'Unmerged transaction {transaction_id}, restored {result["restored_count"]} transactions')
        return jsonify({
            'success': True,
            'restored_ids': result['restored_ids'],
            'restored_count': result['restored_count']
        })

    except Exception as e:
        logger.exception(f'Error unmerging transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@statements_bp.route('/api/transactions/<int:transaction_id>/merged-sources', methods=['GET'])
@api_login_required
def get_merged_sources(transaction_id):
    """
    Get the original transactions that were merged into this transaction.

    Returns:
    {
        "success": true,
        "sources": [
            {"id": 1, "amount": 100, "transaction_date": "2025-01-10", ...},
            {"id": 2, "amount": 200, "transaction_date": "2025-01-12", ...}
        ]
    }
    """
    txn = get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    try:
        sources = get_merged_source_transactions(transaction_id)
        return jsonify({
            'success': True,
            'sources': sources
        })

    except Exception as e:
        logger.exception(f'Error getting merged sources for transaction {transaction_id}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
