"""
e-Factura Duplicate Detection API routes.
"""
from flask import request, jsonify

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required
from ..services.duplicate_service import DuplicateDetectionService
from ..services.invoice_allocation_service import InvoiceAllocationService

_dup_service = DuplicateDetectionService()
_alloc_service = InvoiceAllocationService()


# ============================================================
# API: Duplicate Detection
# ============================================================

@efactura_bp.route('/api/invoices/duplicates', methods=['GET'])
@api_login_required
@efactura_access_required
def get_duplicate_invoices():
    """
    Get list of unallocated e-Factura invoices that are duplicates of existing invoices.

    These are invoices that have the same supplier + invoice_number as an existing
    invoice in the main invoices table.
    """
    try:
        duplicates = _dup_service.detect_unallocated_duplicates()

        return jsonify({
            'success': True,
            'duplicates': duplicates,
            'count': len(duplicates),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/mark-duplicates', methods=['POST'])
@api_login_required
@efactura_access_required
def mark_duplicate_invoices():
    """
    Mark selected e-Factura invoices as duplicates.

    Links them to the existing invoice in the main invoices table.

    Request body:
        invoice_ids: List of e-Factura invoice IDs to mark as duplicates
    """
    try:
        data = request.get_json()
        invoice_ids = data.get('invoice_ids', [])

        if not invoice_ids:
            return jsonify({
                'success': False,
                'error': "No invoices selected",
            }), 400

        result = _dup_service.mark_duplicates(invoice_ids)

        return jsonify({
            'success': True,
            'marked': result.data['marked'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/duplicates/ai', methods=['GET'])
@api_login_required
@efactura_access_required
def get_ai_duplicate_invoices():
    """
    Get list of potential duplicates detected using AI similarity matching.

    This is a fallback when exact supplier+invoice_number matching doesn't find duplicates.
    Uses Claude to analyze similar invoices based on fuzzy name matching and amount proximity.

    Query params:
        limit: Maximum number of invoices to analyze (default: 20, for cost control)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        duplicates = _dup_service.detect_duplicates_with_ai(limit=limit)

        return jsonify({
            'success': True,
            'duplicates': duplicates,
            'count': len(duplicates),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/mark-duplicates/ai', methods=['POST'])
@api_login_required
@efactura_access_required
def mark_ai_duplicate_invoices():
    """
    Mark AI-detected duplicates by linking to specified existing invoices.

    Unlike the regular mark-duplicates endpoint which finds matches by supplier+invoice_number,
    this endpoint uses explicit mappings provided by the AI detection.

    Request body:
        mappings: List of {efactura_id: int, existing_invoice_id: int}
    """
    try:
        data = request.get_json()
        mappings = data.get('mappings', [])

        if not mappings:
            return jsonify({
                'success': False,
                'error': "No mappings provided",
            }), 400

        result = _dup_service.mark_ai_duplicates(mappings)

        return jsonify({
            'success': True,
            'marked': result.data['marked'],
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/ignore', methods=['POST'])
@api_login_required
@efactura_access_required
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

        result = _alloc_service.ignore_invoice(invoice_id, ignored=not restore)

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
        return safe_error_response(e)
