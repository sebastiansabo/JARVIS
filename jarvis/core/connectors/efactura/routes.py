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
    """
    try:
        cif = request.args.get('cif')
        company_id_filter = request.args.get('company_id')
        direction = request.args.get('direction')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)

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
            page=page,
            limit=limit,
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
        from database import save_efactura_oauth_tokens

        token_data = tokens.to_dict()
        save_efactura_oauth_tokens(session_cif, token_data)

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
