"""
e-Factura Invoice Visibility (Hidden + Bin) API routes.
"""
from datetime import date
from flask import request, jsonify

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required, InvoiceDirection
from ..services.invoice_visibility_service import InvoiceVisibilityService

_vis_service = InvoiceVisibilityService()


# ============================================================
# API: Hidden Invoices
# ============================================================

@efactura_bp.route('/api/invoices/hidden', methods=['GET'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.list_hidden_invoices(
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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/hidden/count', methods=['GET'])
@api_login_required
@efactura_access_required
def get_hidden_count():
    """Get count of hidden invoices for badge."""
    try:
        count = _vis_service.get_hidden_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-hide', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.bulk_hide_invoices(invoice_ids)

        return jsonify({
            'success': True,
            'hidden': result.data['hidden'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-restore-hidden', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.bulk_restore_from_hidden(invoice_ids)

        return jsonify({
            'success': True,
            'restored': result.data['restored'],
        })

    except Exception as e:
        return safe_error_response(e)


# ============================================================
# API: Bin (Deleted Invoices)
# ============================================================

@efactura_bp.route('/api/invoices/bin', methods=['GET'])
@api_login_required
@efactura_access_required
def list_deleted_invoices():
    """
    List deleted invoices (bin).

    Query params:
        company_id: Filter by company ID
        direction: 'received' or 'sent'
        start_date: Filter from date (YYYY-MM-DD)
        end_date: Filter to date (YYYY-MM-DD)
        search: Search string
        page: Page number (default 1)
        limit: Page size (default 50, max 200)
    """
    try:
        company_id = request.args.get('company_id', type=int)
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

        result = _vis_service.list_deleted_invoices(
            company_id=company_id,
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
            'companies': result.data['companies'],
            'pagination': result.data['pagination'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bin/count', methods=['GET'])
@api_login_required
@efactura_access_required
def get_bin_count():
    """Get count of deleted invoices for badge."""
    try:
        count = _vis_service.get_bin_count()

        return jsonify({
            'success': True,
            'count': count,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/delete', methods=['POST'])
@api_login_required
@efactura_access_required
def delete_invoice(invoice_id: int):
    """
    Move an invoice to the bin.
    """
    try:
        result = _vis_service.delete_invoice(invoice_id)

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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/restore', methods=['POST'])
@api_login_required
@efactura_access_required
def restore_invoice(invoice_id: int):
    """
    Restore an invoice from the bin.
    """
    try:
        result = _vis_service.restore_from_bin(invoice_id)

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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/permanent-delete', methods=['POST'])
@api_login_required
@efactura_access_required
def permanent_delete_invoice(invoice_id: int):
    """
    Permanently delete an invoice from the bin.
    """
    try:
        result = _vis_service.permanent_delete(invoice_id)

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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-delete', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.bulk_delete_invoices(invoice_ids)

        return jsonify({
            'success': True,
            'deleted': result.data['deleted'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-restore-bin', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.bulk_restore_from_bin(invoice_ids)

        return jsonify({
            'success': True,
            'restored': result.data['restored'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/bulk-permanent-delete', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _vis_service.bulk_permanent_delete(invoice_ids)

        return jsonify({
            'success': True,
            'deleted': result.data['deleted'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/cleanup-old', methods=['POST'])
@api_login_required
@efactura_access_required
def cleanup_old_unallocated():
    """
    Permanently delete unallocated invoices older than N days.

    Request body:
        cif: CIF of the company to clean up
        days: Number of days (default 15)
    """
    try:
        data = request.get_json()
        cif = data.get('cif')
        days = data.get('days', 15)

        if not cif:
            return jsonify({
                'success': False,
                'error': "CIF is required",
            }), 400

        result = _vis_service.cleanup_old_unallocated(days=days, cif_owner=cif)

        return jsonify({
            'success': True,
            'deleted': result.data['deleted'],
        })

    except Exception as e:
        return safe_error_response(e)
