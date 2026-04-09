"""Unified identity / employee mapping API routes.

All endpoints are admin-only. This blueprint is additive — the existing
/sincron/api/* and /biostar/api/* mapping routes remain fully functional.
"""

import logging

from flask import request, jsonify

from core.utils.api_helpers import admin_required, safe_error_response

from . import identity_bp
from .services import UnifiedMappingService


logger = logging.getLogger('jarvis.identity.routes')
service = UnifiedMappingService()


# ── Unified view ──

@identity_bp.route('/api/employees', methods=['GET'])
@admin_required
def get_unified_employees():
    """Per-user unified view + orphan lists + stats."""
    try:
        data = service.get_unified_view()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


@identity_bp.route('/api/stats', methods=['GET'])
@admin_required
def get_stats():
    """Aggregate stats (lightweight)."""
    try:
        stats = service.get_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return safe_error_response(e)


@identity_bp.route('/api/jarvis-users', methods=['GET'])
@admin_required
def get_jarvis_users():
    """Active JARVIS users for manual mapping dropdowns."""
    try:
        users = service.get_jarvis_users()
        return jsonify({'success': True, 'data': users})
    except Exception as e:
        return safe_error_response(e)


# ── Auto-map pipeline ──

@identity_bp.route('/api/auto-map', methods=['POST'])
@admin_required
def auto_map_all():
    """Run the full 5-step Sincron + BioStar auto-map pipeline."""
    try:
        result = service.auto_map_all()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


# ── Manual mapping ──

@identity_bp.route('/api/employees/<int:user_id>/mapping', methods=['PUT'])
@admin_required
def set_mapping(user_id):
    """Manually set a Sincron or BioStar mapping for a JARVIS user.

    Body:
        {
            "source": "sincron" | "biostar",
            "external_id": str,            # sincron_employee_id or biostar_user_id
            "company_name": str            # required for Sincron
        }
    """
    data = request.get_json(silent=True) or {}
    source = data.get('source')
    external_id = data.get('external_id')
    company_name = data.get('company_name')

    if not source or not external_id:
        return jsonify({'success': False,
                        'error': 'source and external_id are required'}), 400

    try:
        result = service.set_mapping(user_id, source, external_id, company_name)
        return jsonify({'success': True, 'data': result,
                        'message': 'Mapping updated'})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return safe_error_response(e)


@identity_bp.route('/api/employees/<int:user_id>/mapping/<source>', methods=['DELETE'])
@admin_required
def remove_mapping(user_id, source):
    """Remove a Sincron or BioStar mapping.

    Query params:
        external_id: sincron_employee_id or biostar_user_id (required)
        company_name: required for Sincron
    """
    external_id = request.args.get('external_id')
    company_name = request.args.get('company_name')

    if not external_id:
        return jsonify({'success': False,
                        'error': 'external_id query param is required'}), 400

    try:
        result = service.remove_mapping(source, external_id, company_name)
        return jsonify({'success': True, 'data': result,
                        'message': 'Mapping removed',
                        'user_id': user_id})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        return safe_error_response(e)
