"""
e-Factura Sync Operations API routes.
"""
import zipfile
import io
from flask import request, jsonify, Response

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_service, efactura_access_required, logger
from ..services.sync_service import EFacturaSyncService

_sync_service = EFacturaSyncService()


# ============================================================
# API: Sync Operations
# ============================================================

@efactura_bp.route('/api/sync/trigger', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _sync_service.trigger_sync(cif)

        return jsonify({
            'success': True,
            'message': result.data['message'],
            'note': result.data['note'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/sync/history', methods=['GET'])
@api_login_required
@efactura_access_required
def get_sync_history():
    """Get sync run history."""
    try:
        cif = request.args.get('cif')
        limit = min(int(request.args.get('limit', 20)), 100)

        runs = _sync_service.get_sync_history(cif, limit)

        return jsonify({
            'success': True,
            'data': runs,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/sync/errors/<run_id>', methods=['GET'])
@api_login_required
@efactura_access_required
def get_sync_errors(run_id: str):
    """Get errors for a sync run."""
    try:
        errors = _sync_service.get_sync_errors(run_id)

        return jsonify({
            'success': True,
            'data': errors,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/sync/stats', methods=['GET'])
@api_login_required
@efactura_access_required
def get_error_stats():
    """Get error statistics for monitoring."""
    try:
        cif = request.args.get('cif')
        hours = int(request.args.get('hours', 24))

        stats = _sync_service.get_error_stats(cif, hours)

        return jsonify({
            'success': True,
            'data': stats,
        })

    except Exception as e:
        return safe_error_response(e)


# ============================================================
# API: Rate Limit Status
# ============================================================

@efactura_bp.route('/api/rate-limit', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


# ============================================================
# API: Live ANAF Fetch (Mock or Real)
# ============================================================

@efactura_bp.route('/api/anaf/messages', methods=['GET'])
@api_login_required
@efactura_access_required
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

        result = _sync_service.fetch_anaf_messages(cif, days, page, filter_type)

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
        return safe_error_response(e)


@efactura_bp.route('/api/anaf/download/<message_id>', methods=['GET'])
@api_login_required
@efactura_access_required
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

        zip_data = _sync_service.download_anaf_message(cif, message_id)
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
        return safe_error_response(e)


@efactura_bp.route('/api/anaf/debug/<message_id>', methods=['GET'])
@api_login_required
@efactura_access_required
def debug_anaf_message(message_id: str):
    """
    Debug endpoint to analyze ANAF message content.

    Downloads the ZIP, extracts all files, and returns their content for analysis.
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        zip_data = _sync_service.download_anaf_message(cif, message_id)

        files_info = []
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            for filename in zf.namelist():
                file_content = zf.read(filename)
                try:
                    content_str = file_content.decode('utf-8')
                    # Truncate large files for display
                    if len(content_str) > 5000:
                        content_str = content_str[:5000] + '\n... [TRUNCATED]'
                except UnicodeDecodeError:
                    content_str = f"[Binary file, {len(file_content)} bytes]"

                files_info.append({
                    'filename': filename,
                    'size': len(file_content),
                    'content': content_str,
                })

        return jsonify({
            'success': True,
            'message_id': message_id,
            'cif': cif,
            'files_count': len(files_info),
            'files': files_info,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/anaf/status', methods=['GET'])
@api_login_required
@efactura_access_required
def anaf_status():
    """Get ANAF client status (mock mode, rate limits, etc.)."""
    try:
        status = efactura_service.get_anaf_status()

        return jsonify({
            'success': True,
            'data': status,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/company/lookup', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/company/lookup-batch', methods=['POST'])
@api_login_required
@efactura_access_required
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
            }), 400

        return jsonify({
            'success': True,
            'data': result.data,
        })

    except Exception as e:
        return safe_error_response(e)


# ============================================================
# API: Import from ANAF
# ============================================================

@efactura_bp.route('/api/import', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _sync_service.import_from_anaf(cif, message_ids)

        return jsonify({
            'success': True,
            'imported': result.data['imported'],
            'skipped': result.data['skipped'],
            'errors': result.data['errors'],
            'company_matched': result.data['company_matched'],
            'company_id': result.data['company_id'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/sync', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _sync_service.sync_all(days=days)

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
        return safe_error_response(e)


@efactura_bp.route('/api/sync/companies', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/sync/company', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _sync_service.sync_single_company(cif, days=days)

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
        return safe_error_response(e)
