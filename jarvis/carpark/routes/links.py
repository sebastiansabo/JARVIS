"""Vehicle Links API routes — cross-module entity linking."""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.repositories.link_repository import VehicleLinkRepository, ALLOWED_ENTITY_TYPES
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize,
    _verify_vehicle_ownership, _user_company_id,
)

logger = logging.getLogger('jarvis.carpark')

_link_repo = VehicleLinkRepository()


@carpark_bp.route('/vehicles/<int:vehicle_id>/links', methods=['GET'])
@login_required
@carpark_required
def get_vehicle_links(vehicle_id):
    """List all linked entities for a vehicle. Query: ?entity_type=invoice"""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    entity_type = request.args.get('entity_type')
    links = _link_repo.get_by_vehicle(vehicle_id, entity_type=entity_type)
    return jsonify({'links': _serialize(links)})


@carpark_bp.route('/vehicles/<int:vehicle_id>/links', methods=['POST'])
@login_required
@carpark_edit_required
def link_entity(vehicle_id):
    """Link an entity to a vehicle.

    Body: { entity_type, entity_id, notes? }
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    entity_type = data.get('entity_type')
    entity_id = data.get('entity_id')
    if not entity_type or not entity_id:
        return jsonify({'error': 'entity_type and entity_id are required'}), 400

    if entity_type not in ALLOWED_ENTITY_TYPES:
        return jsonify({'error': f'Invalid entity_type. Allowed: {", ".join(sorted(ALLOWED_ENTITY_TYPES))}'}), 400

    try:
        link = _link_repo.link(
            vehicle_id, entity_type, int(entity_id),
            linked_by=current_user.id,
            notes=data.get('notes'),
        )
        if link is None:
            return jsonify({'error': 'Link already exists'}), 409
        return jsonify({'link': _serialize(link)}), 201
    except Exception as e:
        logger.error(f'Link creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@carpark_bp.route('/vehicles/<int:vehicle_id>/links/<int:link_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def unlink_entity(vehicle_id, link_id):
    """Remove a link from a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    if _link_repo.unlink(link_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Link not found'}), 404


@carpark_bp.route('/link-search/<entity_type>', methods=['GET'])
@login_required
@carpark_required
def search_linkable_entities(entity_type):
    """Search for entities to link. Query: ?q=search&limit=20"""
    if entity_type not in ALLOWED_ENTITY_TYPES:
        return jsonify({'error': f'Invalid entity_type'}), 400

    q = request.args.get('q', '')
    limit = min(int(request.args.get('limit', '20')), 50)
    company_id = _user_company_id()

    try:
        results = _link_repo.search_entities(entity_type, q, company_id, limit)
        return jsonify({'results': _serialize(results)})
    except Exception as e:
        logger.error(f'Link search failed: {e}', exc_info=True)
        return jsonify({'error': 'Search failed'}), 500
