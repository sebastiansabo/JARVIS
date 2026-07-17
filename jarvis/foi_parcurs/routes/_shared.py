"""Shared imports, blueprint reference, and helpers for Foi de Parcurs routes."""

__all__ = [
    'logging', 'jsonify', 'request', 'g',
    'login_required', 'current_user',
    'foi_parcurs_bp',
    'FoiParcursRepository', 'FPClientRepository', 'FPVehicleRepository',
    'InspectionRepository', 'CrmClientRepository',
    'logger',
    '_fp_repo', '_client_repo', '_vehicle_repo', '_inspection_repo', '_crm_client_repo',
    '_dealer_repo',
]

import logging
from flask import jsonify, request, g
from flask_login import login_required, current_user

from .. import foi_parcurs_bp
from ..repositories import FoiParcursRepository, FPClientRepository, FPVehicleRepository
from ..repositories.inspection_repository import InspectionRepository
from ..repositories.dealer_config_repository import DealerConfigRepository
from crm.repositories import ClientRepository as CrmClientRepository

logger = logging.getLogger('jarvis.foi_parcurs.routes')

_fp_repo = FoiParcursRepository()
_client_repo = FPClientRepository()
_vehicle_repo = FPVehicleRepository()
_inspection_repo = InspectionRepository()
_crm_client_repo = CrmClientRepository()
_dealer_repo = DealerConfigRepository()
