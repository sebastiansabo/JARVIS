"""
e-Factura Company Connections API routes.
"""
from flask import request, jsonify

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_service, efactura_access_required


# ============================================================
# API: Company Connections
# ============================================================

@efactura_bp.route('/api/connections', methods=['GET'])
@api_login_required
@efactura_access_required
def list_connections():
    """List all company connections."""
    try:
        connections = efactura_service.get_all_connections()
        return jsonify({
            'success': True,
            'data': connections,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/connections/<cif>', methods=['GET'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/connections', methods=['POST'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)


@efactura_bp.route('/api/connections/<cif>', methods=['DELETE'])
@api_login_required
@efactura_access_required
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
        return safe_error_response(e)
