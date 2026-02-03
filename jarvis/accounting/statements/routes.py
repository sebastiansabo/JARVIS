"""API routes for Bank Statement module.

Routes call StatementsService for all business logic.
"""
import re
import logging
import time
import csv
import io
from collections import defaultdict
from functools import wraps
from datetime import date
from flask import request, jsonify, render_template, Response
from flask_login import login_required, current_user

from . import statements_bp
from .services import StatementsService

logger = logging.getLogger('jarvis.statements.routes')

# Initialize service
statements_service = StatementsService()


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
        return None, (jsonify({
            'success': False,
            'error': 'Invalid or missing JSON body',
            'details': {'body': 'Request body must be valid JSON'}
        }), 400)
    return data, None


def _validate_upload_files(files: list) -> tuple[bool, str, int]:
    """
    Validate uploaded files for size constraints.

    Returns:
        (is_valid, error_message, total_size)
    """
    total_size = 0
    for file in files:
        if not file.filename:
            continue
        # Get file size by seeking to end
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            return False, f'File {file.filename} exceeds maximum size of 10MB', 0

        total_size += file_size

    if total_size > MAX_TOTAL_SIZE:
        return False, 'Total upload size exceeds maximum of 50MB', total_size

    return True, None, total_size


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
    """
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    # Validate file sizes using helper function
    is_valid, error_msg, _ = _validate_upload_files(files)
    if not is_valid:
        return jsonify({'success': False, 'error': error_msg}), 400

    results = []
    total_new = 0
    total_duplicates = 0
    user_id = current_user.id if current_user.is_authenticated else None

    for file in files:
        if not file.filename:
            continue

        if not file.filename.lower().endswith('.pdf'):
            logger.warning(f'Skipping non-PDF file: {file.filename}')
            continue

        try:
            pdf_bytes = file.read()

            # Process single statement using service
            result = statements_service.process_statement(pdf_bytes, file.filename, user_id)

            if result.success:
                data = result.data
                # Track totals (skipped files don't have these keys)
                if not data.get('skipped'):
                    total_new += data.get('new_transactions', 0)
                    total_duplicates += data.get('duplicate_transactions', 0)
                results.append(data)
            else:
                results.append({
                    'filename': file.filename,
                    'error': result.error
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
    """List all uploaded statements with pagination."""
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    data = statements_service.get_all_statements(limit=limit, offset=offset)

    return jsonify({
        'success': True,
        **data
    })


@statements_bp.route('/api/statements/<int:statement_id>', methods=['GET'])
@api_login_required
def get_statement_detail(statement_id):
    """Get details for a single statement."""
    stmt = statements_service.get_statement(statement_id)
    if not stmt:
        return jsonify({'success': False, 'error': 'Statement not found'}), 404

    return jsonify({'success': True, 'statement': stmt})


@statements_bp.route('/api/statements/<int:statement_id>', methods=['DELETE'])
@api_login_required
def delete_statement_route(statement_id):
    """Delete a statement and all its transactions."""
    result = statements_service.delete_statement(statement_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': result.error}), 404 if result.error == 'Statement not found' else 500


# ============== FILTER OPTIONS ==============

@statements_bp.route('/api/filters', methods=['GET'])
@api_login_required
def get_filter_options():
    """Get available filter options for dropdowns."""
    options = statements_service.get_filter_options()

    return jsonify({
        'success': True,
        **options
    })


# ============== TRANSACTIONS ==============

@statements_bp.route('/api/transactions', methods=['GET'])
@api_login_required
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
def get_single_transaction(transaction_id):
    """Get a single transaction by ID."""
    txn = statements_service.get_transaction(transaction_id)
    if not txn:
        return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    return jsonify({'success': True, 'transaction': txn})


@statements_bp.route('/api/transactions/<int:transaction_id>', methods=['PUT'])
@api_login_required
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


# ============== VENDOR MAPPINGS ==============

@statements_bp.route('/api/mappings', methods=['GET'])
@api_login_required
def list_mappings():
    """List all vendor mappings."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    mappings = statements_service.get_all_mappings(active_only=active_only)

    return jsonify({
        'success': True,
        'mappings': mappings
    })


@statements_bp.route('/api/mappings', methods=['POST'])
@api_login_required
def create_mapping():
    """Create a new vendor mapping."""
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

    result = statements_service.create_mapping(
        pattern=data['pattern'],
        supplier_name=data['supplier_name'],
        supplier_vat=data.get('supplier_vat'),
        template_id=data.get('template_id')
    )

    if result.success:
        return jsonify({
            'success': True,
            'mapping_id': result.data['mapping_id']
        })
    return jsonify({
        'success': False,
        'error': 'Database error',
        'details': {'message': result.error}
    }), 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['GET'])
@api_login_required
def get_single_mapping(mapping_id):
    """Get a single vendor mapping by ID."""
    mapping = statements_service.get_mapping(mapping_id)
    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    return jsonify({'success': True, 'mapping': mapping})


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
@api_login_required
def update_single_mapping(mapping_id):
    """Update a vendor mapping."""
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

    result = statements_service.update_mapping(
        mapping_id,
        pattern=data.get('pattern'),
        supplier_name=data.get('supplier_name'),
        supplier_vat=data.get('supplier_vat'),
        template_id=data.get('template_id'),
        is_active=data.get('is_active')
    )

    if result.success:
        return jsonify({'success': True})
    return jsonify({
        'success': False,
        'error': result.error
    }), 404 if 'not found' in (result.error or '') else 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
@api_login_required
def delete_single_mapping(mapping_id):
    """Delete a vendor mapping."""
    result = statements_service.delete_mapping(mapping_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': result.error}), 400


# ============== INVOICE LINKING ==============

@statements_bp.route('/api/transactions/link-invoice', methods=['POST'])
@api_login_required
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
