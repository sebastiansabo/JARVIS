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
    'open_session_block', 'is_privileged', '_actor', 'log_history',
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


def is_privileged():
    """Admin/superadmin — the override gate for the single-open-session block."""
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


def _actor():
    """Acting user's display name (falls back to email) for a history row;
    None when unauthenticated (e.g. a system/cron mutation)."""
    return getattr(current_user, 'name', None) or getattr(current_user, 'email', None) or None


def log_history(session_id, action):
    """Best-effort append to a session's history log — never raises. An audit
    write must not break the user action that triggered it, so failures (e.g. a
    missing table on a stale DB) are swallowed and logged."""
    try:
        _fp_repo.log_session_event(session_id, action, _actor())
    except Exception:
        logger.warning('session-history log failed for %s (%s)', session_id, action, exc_info=True)


def open_session_block(vin, exclude_id=None, allow_override=False, privileged=False):
    """Single-open-session rule (Rule A): if the car already has an OPEN
    (FILLED) session — TD or Comodat, out and not returned — return a ready 409
    ``(payload, status)`` that blocks starting a new one. The override
    (``allow_override``) is honored ONLY for a privileged (admin) caller.
    Returns None when the car is free or a valid override applies."""
    if allow_override and privileged:
        return None
    s = _fp_repo.get_open_session(vin, exclude_id=exclude_id)
    if not s:
        return None
    who = (s.get('client_name') or s.get('advisor_name') or '').strip()
    rt = 'Comodat' if s.get('route_type') == 'Comodat' else 'Test Drive'
    when = s.get('departure_datetime')
    when_txt = f", din {str(when)[:10]}" if when else ''
    msg = ('Mașina are deja o sesiune în desfășurare (' + rt
           + (f' — {who}' if who else '') + when_txt
           + '). Finalizează returul înainte de a porni una nouă.')
    return ({'success': False, 'error': msg, 'open_session': {
        'id': s['id'], 'route_type': s.get('route_type'),
        'client': who, 'departure': when,
    }}, 409)
