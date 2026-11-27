"""Vehicle query routes — the browser-facing Parc register API.

This is the logged-in-user UI surface (NOT jarvis-alpha's server-to-server
intake feed in routes/intake.py) — gated by `@login_required`, with the
acting company resolved from `current_user` rather than a shared secret.

Phase-1 scope (see spine plan progress.md "spine perm" ruling): simple
same-company read — `current_user.company_id` only, no cross-company acting
switcher yet. Proper `role_permissions_v2` `can_access_logistics` wiring and
any multi-company acting view are Phase-2 (Setări → Utilizatori).

No SQL here (per repo convention) — every query goes through
`LogisticsVehicleRepository.list_vehicles`. Exception mapping mirrors
routes/intake.py's documented convention:
  ValueError      -> 400
  anything else   -> 500 (logged)
"""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from logistics import logistics_bp
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

logger = logging.getLogger('jarvis.logistics')

_vehicle_repo = LogisticsVehicleRepository()

# Query-string keys forwarded straight through to list_vehicles()'s filters
# dict when present and non-empty. location_id is handled separately (needs
# int coercion); company_id is never taken from the client -- it always
# comes from current_user below.
_PASSTHROUGH_FILTER_KEYS = ('q', 'destinatie', 'etapa', 'predare', 'sort', 'dir')


def _user_company_id():
    """The acting company for Parc register reads: the logged-in user's own
    company_id (Phase-1 — see module docstring)."""
    return getattr(current_user, 'company_id', None)


@logistics_bp.route('/api/logistics/vehicles', methods=['GET'])
@login_required
def list_vehicles():
    """Parc register — flat, filterable, sortable vehicle list.

    Query params: q, location_id, destinatie, etapa, predare, sort, dir.
    company_id is never a query param here — it's always the caller's own
    company (see _user_company_id), so a request can't read another
    tenant's register by passing a different id.
    """
    filters = {'company_id': _user_company_id()}

    for key in _PASSTHROUGH_FILTER_KEYS:
        value = request.args.get(key)
        if value:
            filters[key] = value

    location_id_raw = request.args.get('location_id')
    if location_id_raw:
        try:
            filters['location_id'] = int(location_id_raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'location_id must be an integer'}), 400

    try:
        vehicles = _vehicle_repo.list_vehicles(filters)
        return jsonify({'vehicles': vehicles}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(
            'Parc register query failed (company_id=%r, filters=%r): %s',
            filters.get('company_id'), filters, e, exc_info=True,
        )
        return jsonify({'error': 'Internal error'}), 500
