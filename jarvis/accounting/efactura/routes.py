"""
e-Factura API Routes

Flask routes for e-Factura connector UI and API.
"""

from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Optional
from flask import request, jsonify, render_template
from flask_login import login_required, current_user

from core.utils.logging_config import get_logger
from . import accounting_efactura_bp
from .config import InvoiceDirection, ConnectorConfig
from .repositories import (
    CompanyConnectionRepository,
    InvoiceRepository,
    SyncRepository,
)

logger = get_logger('jarvis.accounting.efactura.routes')


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


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


# ============================================================
# UI Routes
# ============================================================

@accounting_efactura_bp.route('/')
@login_required
def index():
    """e-Factura dashboard page."""
    return render_template('accounting/bugetare/efactura.html')


@accounting_efactura_bp.route('/connections')
@login_required
def connections_page():
    """Company connections management page."""
    return render_template('accounting/efactura/connections.html')


@accounting_efactura_bp.route('/invoices')
@login_required
def invoices_page():
    """Invoices list page."""
    return render_template('accounting/efactura/invoices.html')


@accounting_efactura_bp.route('/sync-history')
@login_required
def sync_history_page():
    """Sync history page."""
    return render_template('accounting/efactura/sync_history.html')


# ============================================================
# API: Company Connections
# ============================================================

@accounting_efactura_bp.route('/api/connections', methods=['GET'])
@api_login_required
def list_connections():
    """List all company connections."""
    try:
        repo = CompanyConnectionRepository()
        connections = repo.get_all_active()

        return jsonify({
            'success': True,
            'data': [
                {
                    'id': c.id,
                    'cif': c.cif,
                    'display_name': c.display_name,
                    'environment': c.environment,
                    'status': c.status,
                    'status_message': c.status_message,
                    'last_sync_at': c.last_sync_at.isoformat() if c.last_sync_at else None,
                    'cert_expires_at': c.cert_expires_at.isoformat() if c.cert_expires_at else None,
                    'cert_expiring_soon': c.is_cert_expiring_soon(),
                }
                for c in connections
            ],
        })

    except Exception as e:
        logger.error(f"Error listing connections: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/connections/<cif>', methods=['GET'])
@api_login_required
def get_connection(cif: str):
    """Get connection details by CIF."""
    try:
        repo = CompanyConnectionRepository()
        connection = repo.get_by_cif(cif)

        if connection is None:
            return jsonify({
                'success': False,
                'error': f"Connection not found: {cif}",
            }), 404

        return jsonify({
            'success': True,
            'data': {
                'id': connection.id,
                'cif': connection.cif,
                'display_name': connection.display_name,
                'environment': connection.environment,
                'status': connection.status,
                'status_message': connection.status_message,
                'config': connection.config,
                'last_sync_at': connection.last_sync_at.isoformat() if connection.last_sync_at else None,
                'cert_fingerprint': connection.cert_fingerprint,
                'cert_expires_at': connection.cert_expires_at.isoformat() if connection.cert_expires_at else None,
                'created_at': connection.created_at.isoformat() if connection.created_at else None,
                'updated_at': connection.updated_at.isoformat() if connection.updated_at else None,
            },
        })

    except Exception as e:
        logger.error(f"Error getting connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/connections', methods=['POST'])
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

        from .models import CompanyConnection

        connection = CompanyConnection(
            cif=data['cif'].strip(),
            display_name=data['display_name'].strip(),
            environment=data.get('environment', 'test'),
            status='active',
            config=data.get('config', {}),
        )

        repo = CompanyConnectionRepository()

        # Check if already exists
        existing = repo.get_by_cif(connection.cif)
        if existing:
            return jsonify({
                'success': False,
                'error': f"Connection already exists for CIF: {connection.cif}",
            }), 409

        created = repo.create(connection)

        logger.info(
            "Company connection created via API",
            extra={'cif': created.cif}
        )

        return jsonify({
            'success': True,
            'data': {
                'id': created.id,
                'cif': created.cif,
            },
            'message': 'Connection created successfully',
        }), 201

    except Exception as e:
        logger.error(f"Error creating connection: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/connections/<cif>', methods=['DELETE'])
@api_login_required
def delete_connection(cif: str):
    """Delete a company connection."""
    try:
        repo = CompanyConnectionRepository()
        deleted = repo.delete(cif)

        if not deleted:
            return jsonify({
                'success': False,
                'error': f"Connection not found: {cif}",
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

@accounting_efactura_bp.route('/api/invoices', methods=['GET'])
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
        start = None
        end = None
        if start_date:
            start = date.fromisoformat(start_date)
        if end_date:
            end = date.fromisoformat(end_date)

        repo = InvoiceRepository()
        invoices, total = repo.list_invoices(
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
            'data': [
                {
                    'id': inv.id,
                    'cif_owner': inv.cif_owner,
                    'direction': inv.direction.value,
                    'partner_cif': inv.partner_cif,
                    'partner_name': inv.partner_name,
                    'invoice_number': inv.full_invoice_number,
                    'issue_date': inv.issue_date.isoformat() if inv.issue_date else None,
                    'due_date': inv.due_date.isoformat() if inv.due_date else None,
                    'total_amount': str(inv.total_amount),
                    'total_vat': str(inv.total_vat),
                    'currency': inv.currency,
                    'status': inv.status.value,
                    'created_at': inv.created_at.isoformat() if inv.created_at else None,
                }
                for inv in invoices
            ],
            'pagination': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total,
            },
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


@accounting_efactura_bp.route('/api/invoices/<int:invoice_id>', methods=['GET'])
@api_login_required
def get_invoice(invoice_id: int):
    """Get invoice details with artifacts."""
    try:
        repo = InvoiceRepository()
        invoice = repo.get_by_id(invoice_id)

        if invoice is None:
            return jsonify({
                'success': False,
                'error': f"Invoice not found: {invoice_id}",
            }), 404

        external_ref = repo.get_external_ref(invoice_id)
        artifacts = repo.get_artifacts(invoice_id)

        return jsonify({
            'success': True,
            'data': {
                'id': invoice.id,
                'cif_owner': invoice.cif_owner,
                'direction': invoice.direction.value,
                'partner_cif': invoice.partner_cif,
                'partner_name': invoice.partner_name,
                'invoice_number': invoice.full_invoice_number,
                'invoice_series': invoice.invoice_series,
                'issue_date': invoice.issue_date.isoformat() if invoice.issue_date else None,
                'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
                'total_amount': str(invoice.total_amount),
                'total_vat': str(invoice.total_vat),
                'total_without_vat': str(invoice.total_without_vat),
                'currency': invoice.currency,
                'status': invoice.status.value,
                'created_at': invoice.created_at.isoformat() if invoice.created_at else None,
                'updated_at': invoice.updated_at.isoformat() if invoice.updated_at else None,
                'external_ref': {
                    'message_id': external_ref.message_id,
                    'upload_id': external_ref.upload_id,
                    'download_id': external_ref.download_id,
                    'xml_hash': external_ref.xml_hash,
                } if external_ref else None,
                'artifacts': [
                    {
                        'id': a.id,
                        'type': a.artifact_type.value,
                        'filename': a.original_filename,
                        'size_bytes': a.size_bytes,
                        'checksum': a.checksum,
                    }
                    for a in artifacts
                ],
            },
        })

    except Exception as e:
        logger.error(f"Error getting invoice: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/invoices/<int:invoice_id>/download/<artifact_type>', methods=['GET'])
@api_login_required
def download_artifact(invoice_id: int, artifact_type: str):
    """Download invoice artifact."""
    try:
        from flask import send_file
        from .config import ArtifactType

        # Validate artifact type
        try:
            art_type = ArtifactType(artifact_type)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f"Invalid artifact type: {artifact_type}",
            }), 400

        repo = InvoiceRepository()
        artifact = repo.get_artifact_by_type(invoice_id, art_type)

        if artifact is None:
            return jsonify({
                'success': False,
                'error': f"Artifact not found: {artifact_type}",
            }), 404

        # For now, return the storage URI
        # In production, this would stream from actual storage
        return jsonify({
            'success': True,
            'data': {
                'storage_uri': artifact.storage_uri,
                'filename': artifact.original_filename,
                'mime_type': artifact.mime_type,
            },
        })

    except Exception as e:
        logger.error(f"Error downloading artifact: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/invoices/summary', methods=['GET'])
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

        repo = InvoiceRepository()
        summary = repo.get_summary(cif_owner, start, end)

        return jsonify({
            'success': True,
            'data': {
                'received': {
                    'count': summary['received']['count'],
                    'total': str(summary['received']['total']),
                    'vat': str(summary['received']['vat']),
                },
                'sent': {
                    'count': summary['sent']['count'],
                    'total': str(summary['sent']['total']),
                    'vat': str(summary['sent']['vat']),
                },
            },
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

@accounting_efactura_bp.route('/api/sync/trigger', methods=['POST'])
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

        # For now, return a placeholder
        # In Phase 2, this will trigger the actual sync worker
        logger.info(
            "Manual sync triggered",
            extra={'cif': cif}
        )

        return jsonify({
            'success': True,
            'message': f"Sync triggered for CIF: {cif}",
            'note': "Sync worker not yet implemented (Phase 2)",
        })

    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/sync/history', methods=['GET'])
@api_login_required
def get_sync_history():
    """Get sync run history."""
    try:
        cif = request.args.get('cif')
        limit = min(int(request.args.get('limit', 20)), 100)

        repo = SyncRepository()
        runs = repo.get_recent_runs(cif, limit)

        return jsonify({
            'success': True,
            'data': [
                {
                    'id': r.id,
                    'run_id': r.run_id,
                    'company_cif': r.company_cif,
                    'direction': r.direction,
                    'started_at': r.started_at.isoformat() if r.started_at else None,
                    'finished_at': r.finished_at.isoformat() if r.finished_at else None,
                    'success': r.success,
                    'invoices_created': r.invoices_created,
                    'invoices_skipped': r.invoices_skipped,
                    'errors_count': r.errors_count,
                    'error_summary': r.error_summary,
                }
                for r in runs
            ],
        })

    except Exception as e:
        logger.error(f"Error getting sync history: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/sync/errors/<run_id>', methods=['GET'])
@api_login_required
def get_sync_errors(run_id: str):
    """Get errors for a sync run."""
    try:
        repo = SyncRepository()
        errors = repo.get_run_errors(run_id)

        return jsonify({
            'success': True,
            'data': [
                {
                    'id': e.id,
                    'error_type': e.error_type,
                    'error_code': e.error_code,
                    'error_message': e.error_message,
                    'message_id': e.message_id,
                    'invoice_ref': e.invoice_ref,
                    'is_retryable': e.is_retryable,
                    'created_at': e.created_at.isoformat() if e.created_at else None,
                }
                for e in errors
            ],
        })

    except Exception as e:
        logger.error(f"Error getting sync errors: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@accounting_efactura_bp.route('/api/sync/stats', methods=['GET'])
@api_login_required
def get_error_stats():
    """Get error statistics for monitoring."""
    try:
        cif = request.args.get('cif')
        hours = int(request.args.get('hours', 24))

        repo = SyncRepository()
        stats = repo.get_error_stats(cif, hours)

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

@accounting_efactura_bp.route('/api/rate-limit', methods=['GET'])
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
