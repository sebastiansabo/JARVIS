"""
e-Factura API Routes

Flask routes for e-Factura connector UI and API.
Routes call EFacturaService for all business logic.
"""

from datetime import date
from functools import wraps
from flask import request, jsonify, render_template, Response, redirect, session, url_for
from flask_login import login_required, current_user

from core.utils.logging_config import get_logger
from core.database import get_db, get_cursor, release_db

from . import efactura_bp
from .config import InvoiceDirection, ArtifactType
from .services import EFacturaService
from .services.oauth_service import get_oauth_service, OAuthTokens

logger = get_logger('jarvis.core.connectors.efactura.routes')

# Initialize service
efactura_service = EFacturaService()


def api_login_required(f):
    """Decorator for API endpoints that returns JSON 401 instead of redirect."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
            }), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# UI Routes
# ============================================================

@efactura_bp.route('/')
@login_required
def index():
    """e-Factura dashboard page."""
    return render_template('core/connectors/efactura/index.html')


@efactura_bp.route('/api/migrate-junction-table', methods=['POST'])
@api_login_required
def migrate_junction_table():
    """One-time migration to create the supplier mapping types junction table."""
    try:
        conn = get_db()
        cursor = get_cursor(conn)

        # Create junction table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS efactura_supplier_mapping_types (
                mapping_id INTEGER NOT NULL REFERENCES efactura_supplier_mappings(id) ON DELETE CASCADE,
                type_id INTEGER NOT NULL REFERENCES efactura_partner_types(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (mapping_id, type_id)
            )
        ''')
        conn.commit()

        # Migrate existing type_id data
        cursor.execute('''
            INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
            SELECT id, type_id FROM efactura_supplier_mappings
            WHERE type_id IS NOT NULL
            ON CONFLICT (mapping_id, type_id) DO NOTHING
        ''')
        conn.commit()

        # Count migrated records
        cursor.execute('SELECT COUNT(*) as count FROM efactura_supplier_mapping_types')
        result = cursor.fetchone()
        count = result['count'] if result else 0

        release_db(conn)

        logger.info(f"Junction table migration completed. {count} records in table.")
        return jsonify({
            'success': True,
            'message': f'Junction table created/verified. {count} type mappings exist.'
        })
    except Exception as e:
        logger.error(f"Junction table migration failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@efactura_bp.route('/connections')
@login_required
def connections_page():
    """Company connections management page."""
    return render_template('core/connectors/efactura/connections.html')


@efactura_bp.route('/invoices')
@login_required
def invoices_page():
    """Invoices list page."""
    return render_template('core/connectors/efactura/invoices.html')


@efactura_bp.route('/sync-history')
@login_required
def sync_history_page():
    """Sync history page."""
    return render_template('core/connectors/efactura/sync_history.html')


# ============================================================
# API: Company Connections
# ============================================================

@efactura_bp.route('/api/connections', methods=['GET'])
@api_login_required
def list_connections():
    """List all company connections."""
    try:
        connections = efactura_service.get_all_connections()
        return jsonify({
            'success': True,
            'data': connections,
        })

    except Exception as e:
        logger.error(f"Error listing connections: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/connections/<cif>', methods=['GET'])
@api_login_required
def get_connection(cif: str):
    """Get connection details by CIF."""
    try:
        result = efactura_service.get_connection(cif)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        logger.error(f"Error getting connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/connections', methods=['POST'])
@api_login_required
def create_connection():
    """Create a new company connection."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        required_fields = ['cif', 'display_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f"Missing required field: {field}",
                }), 400

        result = efactura_service.create_connection(
            cif=data['cif'],
            display_name=data['display_name'],
            environment=data.get('environment', 'test'),
            config=data.get('config', {}),
        )

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 409

        return jsonify({
            'success': True,
            'data': result.data,
            'message': 'Connection created successfully',
        }), 201

    except Exception as e:
        logger.error(f"Error creating connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/connections/<cif>', methods=['DELETE'])
@api_login_required
def delete_connection(cif: str):
    """Delete a company connection."""
    try:
        result = efactura_service.delete_connection(cif)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return jsonify({
            'success': True,
            'message': 'Connection deleted successfully',
        })

    except Exception as e:
        logger.error(f"Error deleting connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Invoices
# ============================================================

@efactura_bp.route('/api/invoices', methods=['GET'])
@api_login_required
def list_invoices():
    """List invoices with filters."""
    try:
        # Parse query parameters
        cif_owner = request.args.get('cif')
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        partner_cif = request.args.get('partner_cif')
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))

        if not cif_owner:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Parse direction
        direction_enum = None
        if direction:
            try:
                direction_enum = InvoiceDirection(direction)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': f"Invalid direction: {direction}",
                }), 400

        # Parse dates
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        result = efactura_service.list_invoices(
            cif_owner=cif_owner,
            direction=direction_enum,
            start_date=start,
            end_date=end,
            partner_cif=partner_cif,
            limit=limit,
            offset=offset,
        )

        return jsonify({
            'success': True,
            'data': result.data['invoices'],
            'pagination': result.data['pagination'],
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f"Invalid parameter: {e}",
        }), 400
    except Exception as e:
        logger.error(f"Error listing invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>', methods=['GET'])
@api_login_required
def get_invoice(invoice_id: int):
    """Get invoice details with artifacts."""
    try:
        result = efactura_service.get_invoice(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        logger.error(f"Error getting invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/download/<artifact_type>', methods=['GET'])
@api_login_required
def download_artifact(invoice_id: int, artifact_type: str):
    """Download invoice artifact."""
    try:
        # Validate artifact type
        try:
            art_type = ArtifactType(artifact_type)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f"Invalid artifact type: {artifact_type}",
            }), 400

        result = efactura_service.get_artifact(invoice_id, art_type)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        # For now, return the storage URI
        # In production, this would stream from actual storage
        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        logger.error(f"Error downloading artifact: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/summary', methods=['GET'])
@api_login_required
def get_invoice_summary():
    """Get invoice summary statistics."""
    try:
        cif_owner = request.args.get('cif')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not cif_owner:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        summary = efactura_service.get_invoice_summary(cif_owner, start, end)

        return jsonify({
            'success': True,
            'data': summary,
        })

    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Sync Operations
# ============================================================

@efactura_bp.route('/api/sync/trigger', methods=['POST'])
@api_login_required
def trigger_sync():
    """Manually trigger sync for a company."""
    try:
        data = request.get_json()
        cif = data.get('cif') if data else None

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        result = efactura_service.trigger_sync(cif)

        return jsonify({
            'success': True,
            'message': result.data['message'],
            'note': result.data['note'],
        })

    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync/history', methods=['GET'])
@api_login_required
def get_sync_history():
    """Get sync run history."""
    try:
        cif = request.args.get('cif')
        limit = min(int(request.args.get('limit', 20)), 100)

        runs = efactura_service.get_sync_history(cif, limit)

        return jsonify({
            'success': True,
            'data': runs,
        })

    except Exception as e:
        logger.error(f"Error getting sync history: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync/errors/<run_id>', methods=['GET'])
@api_login_required
def get_sync_errors(run_id: str):
    """Get errors for a sync run."""
    try:
        errors = efactura_service.get_sync_errors(run_id)

        return jsonify({
            'success': True,
            'data': errors,
        })

    except Exception as e:
        logger.error(f"Error getting sync errors: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync/stats', methods=['GET'])
@api_login_required
def get_error_stats():
    """Get error statistics for monitoring."""
    try:
        cif = request.args.get('cif')
        hours = int(request.args.get('hours', 24))

        stats = efactura_service.get_error_stats(cif, hours)

        return jsonify({
            'success': True,
            'data': stats,
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Rate Limit Status
# ============================================================

@efactura_bp.route('/api/rate-limit', methods=['GET'])
@api_login_required
def get_rate_limit():
    """Get current rate limit status."""
    try:
        # This would be populated from the actual client in production
        return jsonify({
            'success': True,
            'data': {
                'max_per_hour': 150,
                'remaining': 150,
                'note': 'Rate limit tracking not yet active (requires sync worker)',
            },
        })

    except Exception as e:
        logger.error(f"Error getting rate limit: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Live ANAF Fetch (Mock or Real)
# ============================================================

@efactura_bp.route('/api/anaf/messages', methods=['GET'])
@api_login_required
def fetch_anaf_messages():
    """
    Fetch messages directly from ANAF API (or mock).

    Query params:
        cif: Company CIF (required)
        days: Look back days (default 60)
        page: Page number (default 1)
        filter: 'received', 'sent', or 'all' (default 'all')
    """
    try:
        cif = request.args.get('cif')
        days = int(request.args.get('days', 60))
        page = int(request.args.get('page', 1))
        filter_param = request.args.get('filter', 'all')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Map filter to ANAF format
        filter_type = None
        if filter_param == 'received':
            filter_type = 'P'
        elif filter_param == 'sent':
            filter_type = 'T'

        result = efactura_service.fetch_anaf_messages(cif, days, page, filter_type)

        if not result.success:
            status_code = 400 if 'Configuration' in (result.error or '') else 500
            return jsonify({
                'success': False,
                'error': result.error,
            }), status_code

        return jsonify({
            'success': True,
            'mock_mode': result.data['mock_mode'],
            'data': {
                'messages': result.data['messages'],
                'pagination': result.data['pagination'],
                'serial': result.data.get('serial'),
                'title': result.data.get('title'),
            },
        })

    except Exception as e:
        logger.error(f"Error fetching ANAF messages: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/anaf/download/<message_id>', methods=['GET'])
@api_login_required
def download_anaf_message(message_id: str):
    """
    Download invoice ZIP from ANAF (or mock).

    Returns the ZIP file as binary data.
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        zip_data = efactura_service.download_anaf_message(cif, message_id)
        status = efactura_service.get_anaf_status()

        return Response(
            zip_data,
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename=invoice_{message_id}.zip',
                'X-Mock-Mode': str(status['mock_mode']).lower(),
            }
        )

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': f"Configuration error: {e}",
        }), 400
    except Exception as e:
        logger.error(f"Error downloading ANAF message: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/anaf/status', methods=['GET'])
@api_login_required
def anaf_status():
    """Get ANAF client status (mock mode, rate limits, etc.)."""
    try:
        status = efactura_service.get_anaf_status()

        return jsonify({
            'success': True,
            'data': status,
        })

    except Exception as e:
        logger.error(f"Error getting ANAF status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/company/lookup', methods=['GET'])
@api_login_required
def lookup_company():
    """
    Lookup company info from ANAF public API by CIF.

    Query params:
        cif: Company CIF (required)

    Returns:
        Company info (name, address, VAT status)
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "CIF parameter is required",
            }), 400

        result = efactura_service.lookup_company_by_cif(cif)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        logger.error(f"Error looking up company: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/company/lookup-batch', methods=['POST'])
@api_login_required
def lookup_companies_batch():
    """
    Lookup multiple companies from ANAF public API.

    Request body:
        cifs: List of CIFs to lookup

    Returns:
        Dict mapping CIF -> company info
    """
    try:
        data = request.get_json()

        if not data or not data.get('cifs'):
            return jsonify({
                'success': False,
                'error': "cifs array is required",
            }), 400

        result = efactura_service.lookup_companies_by_cifs(data['cifs'])

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 500

        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        logger.error(f"Error looking up companies: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Import from ANAF
# ============================================================

@efactura_bp.route('/api/import', methods=['POST'])
@api_login_required
def import_from_anaf():
    """
    Import invoices from ANAF into local storage.

    Request body:
        cif: Company CIF (required)
        message_ids: List of ANAF message IDs to import (required)
    """
    try:
        data = request.get_json()
        cif = data.get('cif')
        message_ids = data.get('message_ids', [])

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        if not message_ids:
            return jsonify({
                'success': False,
                'error': "Missing required field: message_ids",
            }), 400

        result = efactura_service.import_from_anaf(cif, message_ids)

        return jsonify({
            'success': True,
            'imported': result.data['imported'],
            'skipped': result.data['skipped'],
            'errors': result.data['errors'],
            'company_matched': result.data['company_matched'],
            'company_id': result.data['company_id'],
        })

    except Exception as e:
        logger.error(f"Error importing from ANAF: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync', methods=['POST'])
@api_login_required
def sync_all():
    """
    Sync all invoices from all connected companies.

    Fetches messages from ANAF for all active connections and imports them.
    Automatically skips duplicates (already imported invoices).

    Request body (optional):
        days: Number of days to look back (default 60)
    """
    try:
        data = request.get_json() or {}
        days = int(data.get('days', 60))

        result = efactura_service.sync_all(days=days)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            'companies_synced': result.data['companies_synced'],
            'total_fetched': result.data['total_fetched'],
            'total_imported': result.data['total_imported'],
            'total_skipped': result.data['total_skipped'],
            'errors': result.data['errors'],
            'company_results': result.data['company_results'],
        })

    except Exception as e:
        logger.error(f"Error in sync_all: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync/companies', methods=['GET'])
@api_login_required
def get_sync_companies():
    """
    Get list of companies available for sync.

    Returns list of connected companies with their CIF and display name.
    Used by frontend to drive progress-aware sync.
    """
    try:
        connections = efactura_service.get_all_connections()

        return jsonify({
            'success': True,
            'companies': [
                {
                    'cif': c['cif'],
                    'display_name': c.get('display_name', c['cif']),
                }
                for c in connections
            ],
            'count': len(connections),
        })

    except Exception as e:
        logger.error(f"Error getting sync companies: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/sync/company', methods=['POST'])
@api_login_required
def sync_single_company():
    """
    Sync invoices for a single company.

    Request body:
        cif: Company CIF (required)
        days: Number of days to look back (default 60)

    Returns:
        Results for this company's sync operation
    """
    try:
        data = request.get_json() or {}
        cif = data.get('cif')
        days = int(data.get('days', 60))

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        result = efactura_service.sync_single_company(cif, days=days)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            **result.data,
        })

    except Exception as e:
        logger.error(f"Error syncing company: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Unallocated Invoices
# ============================================================

@efactura_bp.route('/api/invoices/unallocated', methods=['GET'])
@api_login_required
def list_unallocated_invoices():
    """
    List invoices that have not been sent to the Invoice Module.

    Query params:
        cif: Filter by company CIF
        company_id: Filter by company ID
        direction: 'received' or 'sent'
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        page: Page number (default 1)
        limit: Page size (default 50, max 200)
        sort_by: Column to sort by (default 'issue_date')
        sort_dir: Sort direction ('asc' or 'desc', default 'desc')
    """
    try:
        cif = request.args.get('cif')
        company_id_filter = request.args.get('company_id')
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)
        sort_by = request.args.get('sort_by', 'issue_date')
        sort_dir = request.args.get('sort_dir', 'desc')

        # Parse direction
        direction_enum = None
        if direction:
            try:
                direction_enum = InvoiceDirection(direction)
            except ValueError:
                pass

        # Parse dates
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        result = efactura_service.list_unallocated_invoices(
            cif_owner=cif,
            company_id=int(company_id_filter) if company_id_filter else None,
            direction=direction_enum,
            start_date=start,
            end_date=end,
            search=search,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        return jsonify({
            'success': True,
            'data': result.data['invoices'],
            'companies': result.data['companies'],
            'pagination': result.data['pagination'],
        })

    except Exception as e:
        logger.error(f"Error listing unallocated invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/unallocated/count', methods=['GET'])
@api_login_required
def get_unallocated_count():
    """Get count of unallocated invoices for badge."""
    try:
        count = efactura_service.get_unallocated_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        logger.error(f"Error getting unallocated count: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/unallocated/ids', methods=['GET'])
@api_login_required
def get_unallocated_ids():
    """Get all IDs of unallocated invoices (for select all functionality)."""
    try:
        company_id = request.args.get('company_id', type=int)
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')

        conn = get_db()
        try:
            cursor = get_cursor(conn)

            where_clauses = ["jarvis_invoice_id IS NULL", "deleted_at IS NULL", "ignored = FALSE"]
            params = {}

            if company_id:
                where_clauses.append("company_id = %(company_id)s")
                params['company_id'] = company_id
            if direction:
                where_clauses.append("direction = %(direction)s")
                params['direction'] = direction
            if start_date:
                where_clauses.append("issue_date >= %(start_date)s")
                params['start_date'] = start_date
            if end_date:
                where_clauses.append("issue_date <= %(end_date)s")
                params['end_date'] = end_date
            if search:
                where_clauses.append("(partner_name ILIKE %(search)s OR invoice_number ILIKE %(search)s)")
                params['search'] = f"%{search}%"

            where_clause = " AND ".join(where_clauses)
            cursor.execute(f"SELECT id FROM efactura_invoices WHERE {where_clause}", params)
            ids = [row['id'] for row in cursor.fetchall()]

            return jsonify({
                'success': True,
                'ids': ids,
                'count': len(ids),
            })
        finally:
            release_db(conn)

    except Exception as e:
        logger.error(f"Error getting unallocated IDs: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/send-to-module', methods=['POST'])
@api_login_required
def send_to_invoice_module():
    """
    Send selected invoices to the main JARVIS Invoice Module.

    Creates records in the main invoices table and marks these as allocated.

    Request body:
        invoice_ids: List of e-Factura invoice IDs to send
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.send_to_invoice_module(invoice_ids)

        return jsonify({
            'success': True,
            'sent': result.data['sent'],
            'errors': result.data['errors'],
        })

    except Exception as e:
        logger.error(f"Error sending to invoice module: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/ignore', methods=['POST'])
@api_login_required
def ignore_invoice(invoice_id: int):
    """
    Mark an invoice as ignored (soft delete).

    This removes the invoice from the unallocated list without deleting it.
    Can be restored later by setting ignored=False.

    Request body (optional):
        restore: Set to true to restore a previously ignored invoice
    """
    try:
        data = request.get_json() or {}
        restore = data.get('restore', False)

        result = efactura_service.ignore_invoice(invoice_id, ignored=not restore)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'ignored': result.data['ignored'],
            'message': 'Invoice restored' if restore else 'Invoice ignored',
        })

    except Exception as e:
        logger.error(f"Error ignoring invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Hidden Invoices
# ============================================================

@efactura_bp.route('/api/invoices/hidden', methods=['GET'])
@api_login_required
def list_hidden_invoices():
    """
    List hidden (ignored) invoices.

    Query params:
        direction: 'received' or 'sent'
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        search: Search string
        page: Page number (default 1)
        limit: Page size (default 50, max 200)
    """
    try:
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)

        direction_enum = None
        if direction:
            try:
                direction_enum = InvoiceDirection(direction)
            except ValueError:
                pass

        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        result = efactura_service.list_hidden_invoices(
            direction=direction_enum,
            start_date=start,
            end_date=end,
            search=search,
            page=page,
            limit=limit,
        )

        return jsonify({
            'success': True,
            'data': result.data['invoices'],
            'pagination': result.data['pagination'],
        })

    except Exception as e:
        logger.error(f"Error listing hidden invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/hidden/count', methods=['GET'])
@api_login_required
def get_hidden_count():
    """Get count of hidden invoices for badge."""
    try:
        count = efactura_service.get_hidden_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        logger.error(f"Error getting hidden count: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bulk-hide', methods=['POST'])
@api_login_required
def bulk_hide_invoices():
    """
    Hide multiple invoices.

    Request body:
        invoice_ids: List of invoice IDs to hide
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.bulk_hide_invoices(invoice_ids)

        return jsonify({
            'success': True,
            'hidden': result.data['hidden'],
        })

    except Exception as e:
        logger.error(f"Error bulk hiding invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bulk-restore-hidden', methods=['POST'])
@api_login_required
def bulk_restore_from_hidden():
    """
    Restore multiple invoices from hidden.

    Request body:
        invoice_ids: List of invoice IDs to restore
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.bulk_restore_from_hidden(invoice_ids)

        return jsonify({
            'success': True,
            'restored': result.data['restored'],
        })

    except Exception as e:
        logger.error(f"Error bulk restoring invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Bin (Deleted Invoices)
# ============================================================

@efactura_bp.route('/api/invoices/bin', methods=['GET'])
@api_login_required
def list_deleted_invoices():
    """
    List deleted invoices (bin).

    Query params:
        direction: 'received' or 'sent'
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        search: Search string
        page: Page number (default 1)
        limit: Page size (default 50, max 200)
    """
    try:
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        search = request.args.get('search')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)

        direction_enum = None
        if direction:
            try:
                direction_enum = InvoiceDirection(direction)
            except ValueError:
                pass

        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        result = efactura_service.list_deleted_invoices(
            direction=direction_enum,
            start_date=start,
            end_date=end,
            search=search,
            page=page,
            limit=limit,
        )

        return jsonify({
            'success': True,
            'data': result.data['invoices'],
            'pagination': result.data['pagination'],
        })

    except Exception as e:
        logger.error(f"Error listing deleted invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bin/count', methods=['GET'])
@api_login_required
def get_bin_count():
    """Get count of deleted invoices for badge."""
    try:
        count = efactura_service.get_bin_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        logger.error(f"Error getting bin count: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/delete', methods=['POST'])
@api_login_required
def delete_invoice(invoice_id: int):
    """
    Move an invoice to the bin.
    """
    try:
        result = efactura_service.delete_invoice(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'message': 'Invoice moved to bin',
        })

    except Exception as e:
        logger.error(f"Error deleting invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/restore', methods=['POST'])
@api_login_required
def restore_invoice(invoice_id: int):
    """
    Restore an invoice from the bin.
    """
    try:
        result = efactura_service.restore_from_bin(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'message': 'Invoice restored from bin',
        })

    except Exception as e:
        logger.error(f"Error restoring invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/permanent-delete', methods=['POST'])
@api_login_required
def permanent_delete_invoice(invoice_id: int):
    """
    Permanently delete an invoice from the bin.
    """
    try:
        result = efactura_service.permanent_delete(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 400

        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'message': 'Invoice permanently deleted',
        })

    except Exception as e:
        logger.error(f"Error permanently deleting invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bulk-delete', methods=['POST'])
@api_login_required
def bulk_delete_invoices():
    """
    Move multiple invoices to the bin.

    Request body:
        invoice_ids: List of invoice IDs to delete
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.bulk_delete_invoices(invoice_ids)

        return jsonify({
            'success': True,
            'deleted': result.data['deleted'],
        })

    except Exception as e:
        logger.error(f"Error bulk deleting invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bulk-restore-bin', methods=['POST'])
@api_login_required
def bulk_restore_from_bin():
    """
    Restore multiple invoices from the bin.

    Request body:
        invoice_ids: List of invoice IDs to restore
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.bulk_restore_from_bin(invoice_ids)

        return jsonify({
            'success': True,
            'restored': result.data['restored'],
        })

    except Exception as e:
        logger.error(f"Error bulk restoring invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/bulk-permanent-delete', methods=['POST'])
@api_login_required
def bulk_permanent_delete_invoices():
    """
    Permanently delete multiple invoices from the bin.

    Request body:
        invoice_ids: List of invoice IDs to permanently delete
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = efactura_service.bulk_permanent_delete(invoice_ids)

        return jsonify({
            'success': True,
            'deleted': result.data['deleted'],
        })

    except Exception as e:
        logger.error(f"Error bulk permanently deleting invoices: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/invoices/<int:invoice_id>/pdf', methods=['GET'])
@api_login_required
def get_invoice_pdf(invoice_id: int):
    """
    Get PDF for a stored e-Factura invoice.

    Retrieves the XML from storage and converts to PDF via ANAF API.
    """
    try:
        result = efactura_service.get_invoice_pdf(invoice_id)

        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error,
            }), 404

        return Response(
            result.data['pdf_data'],
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={result.data["filename"]}',
            }
        )

    except Exception as e:
        logger.error(f"Error getting invoice PDF: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/anaf/export-pdf/<message_id>', methods=['GET'])
@api_login_required
def export_invoice_pdf(message_id: str):
    """
    Export invoice as PDF.

    Downloads the ZIP from ANAF, extracts the XML, and converts it to PDF
    using ANAF's official XML-to-PDF transformation API.

    Query params:
        cif: Company CIF (required)
        standard: 'FACT1' (invoice) or 'FCN' (credit note), default 'FACT1'
        validate: 'true' or 'false', default 'true'
    """
    try:
        cif = request.args.get('cif')
        standard = request.args.get('standard', 'FACT1')
        validate = request.args.get('validate', 'true').lower() == 'true'

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        if standard not in ('FACT1', 'FCN'):
            return jsonify({
                'success': False,
                'error': "Invalid standard. Must be 'FACT1' or 'FCN'",
            }), 400

        result = efactura_service.export_anaf_pdf(cif, message_id, standard, validate)

        if not result.success:
            status_code = 400 if 'Configuration' in (result.error or '') else 500
            return jsonify({
                'success': False,
                'error': result.error,
            }), status_code

        return Response(
            result.data['pdf_data'],
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={result.data["filename"]}',
                'X-Mock-Mode': str(result.data['mock_mode']).lower(),
            }
        )

    except Exception as e:
        logger.error(f"Error exporting PDF: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: OAuth2 Authentication
# ============================================================

@efactura_bp.route('/oauth/authorize', methods=['GET'])
@login_required
def oauth_authorize():
    """
    Initiate OAuth2 flow with ANAF.

    Query params:
        cif: Company CIF (required)

    Redirects user to ANAF login page where they authenticate with USB token.
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Clean CIF (remove RO prefix if present)
        clean_cif = cif.upper().replace('RO', '').strip()

        # Get OAuth service and generate authorization URL
        oauth_service = get_oauth_service()
        auth_url, state = oauth_service.get_authorization_url(clean_cif)

        # Store state in session for callback validation
        session['oauth_state'] = state
        session['oauth_cif'] = clean_cif

        logger.info(
            "Initiating OAuth flow",
            extra={'cif': clean_cif, 'state': state[:8] + '...'}
        )

        # Redirect to ANAF login page
        return redirect(auth_url)

    except Exception as e:
        logger.error(f"Error initiating OAuth: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/oauth/callback', methods=['GET'])
@efactura_bp.route('/callback', methods=['GET'])  # Also handle /efactura/callback (ANAF registration)
@login_required
def oauth_callback():
    """
    Handle OAuth2 callback from ANAF.

    Query params (from ANAF):
        code: Authorization code
        state: State parameter for CSRF protection

    Exchanges code for tokens and stores them in database.
    """
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        error_description = request.args.get('error_description')

        # Check for error from ANAF
        if error:
            logger.error(
                "OAuth error from ANAF",
                extra={'error': error, 'description': error_description}
            )
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error=error_description or error,
            )

        if not code or not state:
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error="Missing authorization code or state parameter",
            )

        # Validate state matches session
        session_state = session.get('oauth_state')
        session_cif = session.get('oauth_cif')

        if not session_state or state != session_state:
            logger.warning(
                "OAuth state mismatch",
                extra={'expected': session_state[:8] + '...' if session_state else 'None'}
            )
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error="Invalid state parameter. Please try again.",
            )

        # Exchange code for tokens
        oauth_service = get_oauth_service()

        # Restore pending auth data from session if needed
        pending = oauth_service.get_pending_auth(state)
        if not pending and session_cif:
            # Restore from session (in case of server restart)
            oauth_service.store_pending_auth(state, {
                'code_verifier': session.get('oauth_code_verifier', ''),
                'cif': session_cif,
                'created_at': session.get('oauth_created_at', ''),
            })

        tokens = oauth_service.exchange_code_for_tokens(code, state)

        # Store tokens in database
        from database import save_efactura_oauth_tokens, get_db, get_cursor, release_db

        token_data = tokens.to_dict()
        save_efactura_oauth_tokens(session_cif, token_data)

        # Auto-create company connection if it doesn't exist
        try:
            conn = get_db()
            cursor = get_cursor(conn)

            # Check if connection already exists
            cursor.execute(
                'SELECT id FROM efactura_company_connections WHERE cif = %s',
                (session_cif,)
            )
            existing = cursor.fetchone()

            if not existing:
                # Try to find company name from companies table
                cursor.execute(
                    'SELECT company FROM companies WHERE vat LIKE %s',
                    (f'%{session_cif}%',)
                )
                company_row = cursor.fetchone()
                display_name = company_row['company'] if company_row else f'CIF {session_cif}'

                # Create connection record
                cursor.execute('''
                    INSERT INTO efactura_company_connections
                    (cif, display_name, environment, status, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                ''', (session_cif, display_name, 'production', 'active'))
                conn.commit()

                logger.info(
                    "Auto-created company connection",
                    extra={'cif': session_cif, 'display_name': display_name}
                )

            release_db(conn)
        except Exception as conn_err:
            logger.warning(f"Could not auto-create connection: {conn_err}")

        # Clear session data
        session.pop('oauth_state', None)
        session.pop('oauth_cif', None)
        session.pop('oauth_code_verifier', None)
        session.pop('oauth_created_at', None)

        logger.info(
            "OAuth flow completed successfully",
            extra={'cif': session_cif}
        )

        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=True,
            cif=session_cif,
            expires_at=tokens.expires_at.isoformat(),
        )

    except ValueError as e:
        logger.error(f"OAuth token exchange failed: {e}")
        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=False,
            error=f"An unexpected error occurred: {e}",
        )


@efactura_bp.route('/oauth/revoke', methods=['POST'])
@api_login_required
def oauth_revoke():
    """
    Revoke OAuth tokens and disconnect from ANAF.

    Request body:
        cif: Company CIF (required)
    """
    try:
        data = request.get_json()
        cif = data.get('cif') if data else None

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        # Get current tokens to revoke
        from database import get_efactura_oauth_tokens, delete_efactura_oauth_tokens

        tokens = get_efactura_oauth_tokens(clean_cif)

        if tokens and tokens.get('refresh_token'):
            # Revoke token at ANAF
            oauth_service = get_oauth_service()
            oauth_service.revoke_token(tokens['refresh_token'])

        # Delete from database
        deleted = delete_efactura_oauth_tokens(clean_cif)

        if deleted:
            logger.info(
                "OAuth tokens revoked",
                extra={'cif': clean_cif}
            )
            return jsonify({
                'success': True,
                'message': 'Disconnected successfully',
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No active connection found',
            }), 404

    except Exception as e:
        logger.error(f"Error revoking OAuth tokens: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/oauth/status', methods=['GET'])
@api_login_required
def oauth_status():
    """
    Get OAuth authentication status for a company.

    Query params:
        cif: Company CIF (required)

    Returns:
        authenticated: Whether valid tokens exist
        expires_at: Token expiration time (if authenticated)
        expires_in_seconds: Seconds until expiration
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        from database import get_efactura_oauth_status

        status = get_efactura_oauth_status(clean_cif)

        return jsonify({
            'success': True,
            'data': status,
        })

    except Exception as e:
        logger.error(f"Error getting OAuth status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/oauth/refresh', methods=['POST'])
@api_login_required
def oauth_refresh():
    """
    Manually refresh OAuth access token.

    Request body:
        cif: Company CIF (required)

    Normally tokens auto-refresh, but this endpoint allows manual refresh.
    """
    try:
        data = request.get_json()
        cif = data.get('cif') if data else None

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        from database import get_efactura_oauth_tokens, save_efactura_oauth_tokens

        tokens = get_efactura_oauth_tokens(clean_cif)

        if not tokens or not tokens.get('refresh_token'):
            return jsonify({
                'success': False,
                'error': 'No active connection found. Please authenticate first.',
            }), 404

        # Refresh the token
        oauth_service = get_oauth_service()
        new_tokens = oauth_service.refresh_access_token(
            tokens['refresh_token'],
            clean_cif
        )

        # Save new tokens
        save_efactura_oauth_tokens(clean_cif, new_tokens.to_dict())

        logger.info(
            "OAuth tokens refreshed manually",
            extra={'cif': clean_cif}
        )

        return jsonify({
            'success': True,
            'message': 'Token refreshed successfully',
            'expires_at': new_tokens.expires_at.isoformat(),
        })

    except ValueError as e:
        logger.error(f"Token refresh failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 400
    except Exception as e:
        logger.error(f"Error refreshing OAuth token: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Supplier Mappings
# ============================================================

from .repositories.invoice_repo import SupplierMappingRepository

supplier_mapping_repo = SupplierMappingRepository()


@efactura_bp.route('/api/mappings', methods=['GET'])
@api_login_required
def list_supplier_mappings():
    """
    List all supplier mappings.

    Query params:
        active_only: Whether to show only active mappings (default true)
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        mappings = supplier_mapping_repo.get_all(active_only=active_only)

        return jsonify({
            'success': True,
            'mappings': mappings,
            'count': len(mappings),
        })

    except Exception as e:
        logger.error(f"Error listing supplier mappings: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['GET'])
@api_login_required
def get_supplier_mapping(mapping_id: int):
    """Get a single supplier mapping by ID."""
    try:
        mapping = supplier_mapping_repo.get_by_id(mapping_id)

        if not mapping:
            return jsonify({
                'success': False,
                'error': 'Mapping not found',
            }), 404

        return jsonify({
            'success': True,
            'mapping': mapping,
        })

    except Exception as e:
        logger.error(f"Error getting supplier mapping: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings', methods=['POST'])
@api_login_required
def create_supplier_mapping():
    """
    Create a new supplier mapping.

    Request body:
        partner_name: The e-Factura partner name (required)
        supplier_name: The standardized supplier name (required)
        partner_cif: Optional VAT number from e-Factura
        supplier_note: Optional notes about the supplier
        supplier_vat: The standardized VAT number
        kod_konto: The accounting code
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        partner_name = data.get('partner_name', '').strip()
        supplier_name = data.get('supplier_name', '').strip()

        if not partner_name:
            return jsonify({
                'success': False,
                'error': "partner_name is required",
            }), 400

        if not supplier_name:
            return jsonify({
                'success': False,
                'error': "supplier_name is required",
            }), 400

        # Handle type_ids array (new) or type_id (legacy)
        type_ids = data.get('type_ids')
        type_id = data.get('type_id')

        # Convert type_ids to list of ints
        if type_ids is not None:
            try:
                type_ids = [int(tid) for tid in type_ids if tid]
            except (ValueError, TypeError):
                type_ids = []
        elif type_id is not None:
            # Legacy: convert single type_id to list
            try:
                type_ids = [int(type_id)] if type_id else []
            except (ValueError, TypeError):
                type_ids = []

        mapping_id = supplier_mapping_repo.create(
            partner_name=partner_name,
            supplier_name=supplier_name,
            partner_cif=data.get('partner_cif', '').strip() or None,
            supplier_note=data.get('supplier_note', '').strip() or None,
            supplier_vat=data.get('supplier_vat', '').strip() or None,
            kod_konto=data.get('kod_konto', '').strip() or None,
            type_ids=type_ids,
        )

        return jsonify({
            'success': True,
            'id': mapping_id,
            'message': 'Mapping created successfully',
        }), 201

    except Exception as e:
        logger.error(f"Error creating supplier mapping: {e}")
        # Check for unique constraint violation
        if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'A mapping for this partner already exists',
            }), 409
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
@api_login_required
def update_supplier_mapping(mapping_id: int):
    """
    Update a supplier mapping.

    Request body:
        partner_name: New partner name
        partner_cif: New partner CIF
        supplier_name: New supplier name
        supplier_note: New supplier note
        supplier_vat: New supplier VAT
        kod_konto: New accounting code
        is_active: Whether mapping is active
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        # Handle type_ids array (new) or type_id (legacy)
        type_ids = None
        if 'type_ids' in data:
            # type_ids explicitly provided (can be empty array to clear types)
            try:
                type_ids = [int(tid) for tid in data['type_ids'] if tid]
            except (ValueError, TypeError):
                type_ids = []
        elif 'type_id' in data:
            # Legacy: convert single type_id to list
            type_id = data.get('type_id')
            try:
                type_ids = [int(type_id)] if type_id else []
            except (ValueError, TypeError):
                type_ids = []

        success = supplier_mapping_repo.update(
            mapping_id,
            partner_name=data.get('partner_name'),
            partner_cif=data.get('partner_cif'),
            supplier_name=data.get('supplier_name'),
            supplier_note=data.get('supplier_note'),
            supplier_vat=data.get('supplier_vat'),
            kod_konto=data.get('kod_konto'),
            type_ids=type_ids,
            is_active=data.get('is_active'),
        )

        if not success:
            return jsonify({
                'success': False,
                'error': 'Mapping not found or update failed',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Mapping updated successfully',
        })

    except Exception as e:
        logger.error(f"Error updating supplier mapping: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
@api_login_required
def delete_supplier_mapping(mapping_id: int):
    """Delete a supplier mapping."""
    try:
        success = supplier_mapping_repo.delete(mapping_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Mapping not found',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Mapping deleted successfully',
        })

    except Exception as e:
        logger.error(f"Error deleting supplier mapping: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/partners/distinct', methods=['GET'])
@api_login_required
def get_distinct_partners():
    """
    Get distinct partner names and CIFs from e-Factura invoices.

    Returns list of distinct partner name/CIF combinations for auto-suggest.
    """
    try:
        partners = supplier_mapping_repo.get_distinct_partners()

        return jsonify({
            'success': True,
            'partners': partners,
            'count': len(partners),
        })

    except Exception as e:
        logger.error(f"Error getting distinct partners: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/lookup', methods=['GET'])
@api_login_required
def lookup_supplier_mapping():
    """
    Find a mapping for a partner name/CIF combination.

    Query params:
        partner_name: Partner name to look up (required)
        partner_cif: Partner CIF (optional, improves match accuracy)

    Returns:
        The matching mapping if found, or null
    """
    try:
        partner_name = request.args.get('partner_name', '').strip()
        partner_cif = request.args.get('partner_cif', '').strip() or None

        if not partner_name:
            return jsonify({
                'success': False,
                'error': "partner_name is required",
            }), 400

        mapping = supplier_mapping_repo.find_by_partner(partner_name, partner_cif)

        return jsonify({
            'success': True,
            'mapping': mapping,
            'found': mapping is not None,
        })

    except Exception as e:
        logger.error(f"Error looking up supplier mapping: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/bulk-delete', methods=['POST'])
@api_login_required
def bulk_delete_supplier_mappings():
    """
    Bulk delete supplier mappings.

    Request body:
        {
            "ids": [1, 2, 3]
        }

    Returns:
        Number of mappings deleted
    """
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])

        if not ids:
            return jsonify({
                'success': False,
                'error': "No mapping IDs provided",
            }), 400

        deleted_count = 0
        for mapping_id in ids:
            if supplier_mapping_repo.delete(mapping_id):
                deleted_count += 1

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f"Deleted {deleted_count} mapping(s)",
        })

    except Exception as e:
        logger.error(f"Error bulk deleting supplier mappings: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/mappings/bulk-set-type', methods=['POST'])
@api_login_required
def bulk_set_mappings_type():
    """
    Bulk set type for supplier mappings.

    Request body:
        {
            "ids": [1, 2, 3],
            "type_name": "Service" or "Merchandise" or null
        }

    Returns:
        Number of mappings updated
    """
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])
        type_name = data.get('type_name')  # Can be None to clear type

        if not ids:
            return jsonify({
                'success': False,
                'error': "No mapping IDs provided",
            }), 400

        # Get type_id from type_name
        type_id = None
        if type_name:
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute(
                    "SELECT id FROM efactura_partner_types WHERE name = %s AND is_active = TRUE",
                    (type_name,)
                )
                row = cursor.fetchone()
                if row:
                    type_id = row['id']
                else:
                    return jsonify({
                        'success': False,
                        'error': f"Type '{type_name}' not found",
                    }), 400
            finally:
                release_db(conn)

        # Update all mappings
        updated_count = 0
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            for mapping_id in ids:
                cursor.execute(
                    "UPDATE efactura_supplier_mappings SET type_id = %s, updated_at = NOW() WHERE id = %s",
                    (type_id, mapping_id)
                )
                if cursor.rowcount > 0:
                    updated_count += 1
            conn.commit()
        finally:
            release_db(conn)

        return jsonify({
            'success': True,
            'updated': updated_count,
            'message': f"Updated {updated_count} mapping(s)",
        })

    except Exception as e:
        logger.error(f"Error bulk setting type for mappings: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


# ============================================================
# API: Partner Types
# ============================================================

from .repositories.invoice_repo import PartnerTypeRepository

partner_type_repo = PartnerTypeRepository()


@efactura_bp.route('/api/partner-types', methods=['GET'])
@api_login_required
def list_partner_types():
    """
    List all partner types.

    Query params:
        active_only: Whether to show only active types (default true)
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        types = partner_type_repo.get_all(active_only=active_only)

        return jsonify({
            'success': True,
            'types': types,
            'count': len(types),
        })

    except Exception as e:
        logger.error(f"Error listing partner types: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['GET'])
@api_login_required
def get_partner_type(type_id: int):
    """Get a single partner type by ID."""
    try:
        partner_type = partner_type_repo.get_by_id(type_id)

        if not partner_type:
            return jsonify({
                'success': False,
                'error': 'Partner type not found',
            }), 404

        return jsonify({
            'success': True,
            'type': partner_type,
        })

    except Exception as e:
        logger.error(f"Error getting partner type: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/partner-types', methods=['POST'])
@api_login_required
def create_partner_type():
    """
    Create a new partner type.

    Request body:
        name: The type name (required)
        description: Optional description
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        name = data.get('name', '').strip()

        if not name:
            return jsonify({
                'success': False,
                'error': "name is required",
            }), 400

        type_id = partner_type_repo.create(
            name=name,
            description=data.get('description', '').strip() or None,
        )

        return jsonify({
            'success': True,
            'id': type_id,
            'message': 'Partner type created successfully',
        }), 201

    except Exception as e:
        logger.error(f"Error creating partner type: {e}")
        # Check for unique constraint violation
        if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'A partner type with this name already exists',
            }), 409
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['PUT'])
@api_login_required
def update_partner_type(type_id: int):
    """
    Update a partner type.

    Request body:
        name: New name
        description: New description
        is_active: Whether type is active
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        success = partner_type_repo.update(
            type_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
        )

        if not success:
            return jsonify({
                'success': False,
                'error': 'Partner type not found or update failed',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Partner type updated successfully',
        })

    except Exception as e:
        logger.error(f"Error updating partner type: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['DELETE'])
@api_login_required
def delete_partner_type(type_id: int):
    """Delete a partner type (soft delete)."""
    try:
        success = partner_type_repo.delete(type_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Partner type not found',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Partner type deleted successfully',
        })

    except Exception as e:
        logger.error(f"Error deleting partner type: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500
