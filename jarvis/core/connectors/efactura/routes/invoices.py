"""
e-Factura Invoice list/detail API routes.
"""
from datetime import date
from flask import request, jsonify, Response

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_service, efactura_access_required, ArtifactType, InvoiceDirection


# ============================================================
# API: Invoices
# ============================================================

@efactura_bp.route('/api/invoices', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/<int:invoice_id>/download/<artifact_type>', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/invoices/summary', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)
