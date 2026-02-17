"""Marketing admin routes — KPI definitions catalog."""

import logging
from flask import jsonify, request
from flask_login import login_required

from marketing import marketing_bp
from marketing.repositories import KpiRepository
from core.utils.api_helpers import admin_required, get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.admin')

_kpi_repo = KpiRepository()


@marketing_bp.route('/api/kpi-definitions', methods=['GET'])
@login_required
def api_get_kpi_definitions():
    """Get all KPI definitions (catalog) with extracted formula variables."""
    from marketing.services.formula_engine import extract_variables
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    definitions = _kpi_repo.get_definitions(active_only=active_only)
    for d in definitions:
        d['variables'] = extract_variables(d.get('formula'))
    return jsonify({'definitions': definitions})


@marketing_bp.route('/api/kpi-definitions', methods=['POST'])
@admin_required
def api_create_kpi_definition():
    """Create a new KPI definition (admin only)."""
    data, error = get_json_or_error()
    if error:
        return error

    name = data.get('name')
    slug = data.get('slug')
    if not name or not slug:
        return jsonify({'success': False, 'error': 'name and slug are required'}), 400

    try:
        def_id = _kpi_repo.create_definition(
            name=name,
            slug=slug,
            unit=data.get('unit', 'number'),
            direction=data.get('direction', 'higher'),
            category=data.get('category', 'performance'),
            formula=data.get('formula'),
            description=data.get('description'),
        )
        return jsonify({'success': True, 'id': def_id}), 201
    except Exception as e:
        if 'mkt_kpi_definitions_slug_key' in str(e):
            return jsonify({'success': False, 'error': 'A KPI with that slug already exists'}), 409
        return safe_error_response(e)


@marketing_bp.route('/api/kpi-definitions/<int:def_id>', methods=['PUT'])
@admin_required
def api_update_kpi_definition(def_id):
    """Update a KPI definition (admin only)."""
    data, error = get_json_or_error()
    if error:
        return error

    try:
        updated = _kpi_repo.update_definition(def_id, **data)
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'KPI definition not found'}), 404
    except Exception as e:
        if 'mkt_kpi_definitions_slug_key' in str(e):
            return jsonify({'success': False, 'error': 'A KPI with that slug already exists'}), 409
        return safe_error_response(e)


@marketing_bp.route('/api/kpi-formulas/validate', methods=['POST'])
@login_required
def api_validate_formula():
    """Validate a formula and return its extracted variables."""
    from marketing.services.formula_engine import validate as validate_formula
    data, error = get_json_or_error()
    if error:
        return error
    formula = data.get('formula', '')
    is_valid, err, variables = validate_formula(formula)
    return jsonify({'valid': is_valid, 'error': err, 'variables': variables})
