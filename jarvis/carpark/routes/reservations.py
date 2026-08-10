"""Reservation API routes — cancel + history, on top of DispoService/
ReservationRepository. No SQL here (per repo convention).

Exception mapping mirrors dispo.py / DispoService's documented convention:
  PermissionError -> 403 (cross-tenant vehicle)
  ValueError      -> 400 (validation / guard failure)
  anything else   -> 500 (logged)
"""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.repositories.reservation_repository import ReservationRepository
from carpark.services.dispo_service import DispoService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required,
    _serialize, _verify_vehicle_ownership, _user_company_id,
)

logger = logging.getLogger('jarvis.carpark')

_dispo_service = DispoService()
_reservation_repo = ReservationRepository()


@carpark_bp.route('/vehicles/<int:vehicle_id>/cancel-reservation', methods=['POST'])
@login_required
@carpark_edit_required
def cancel_reservation(vehicle_id):
    """Cancel the vehicle's active reservation and restore its prior status.
    Body: {reason}"""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    try:
        result = _dispo_service.cancel_reservation(
            vehicle_id, _user_company_id(), current_user, reason=data.get('reason'))
        return jsonify(_serialize(result))
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Cancel reservation failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@carpark_bp.route('/vehicles/<int:vehicle_id>/reservations', methods=['GET'])
@login_required
@carpark_required
def list_vehicle_reservations(vehicle_id):
    """Full reservation history (any status) for a vehicle, most recent first."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    try:
        reservations = _reservation_repo.list_for_vehicle(vehicle_id)
        return jsonify({'reservations': _serialize(reservations)})
    except Exception as e:
        logger.error(f'List reservations failed for vehicle {vehicle_id}: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500
