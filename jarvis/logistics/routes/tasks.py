"""Kanban board routes — the browser-facing Panou de lucru API (read-only
for now; the move action is Task 8, which ADDS a POST .../move route here).

Same surface as routes/vehicles.py (NOT jarvis-alpha's server-to-server
intake feed in routes/intake.py) — gated by `@login_required`, with the
acting company resolved from `current_user` via the shared
`_user_company_id()` helper (imported from vehicles.py — see that module's
docstring for the Phase-1 scope this rides on).

No SQL here (per repo convention) — every query goes through
`TaskRepository.get_board`. Exception mapping mirrors routes/vehicles.py's
documented convention:
  ValueError      -> 400
  anything else   -> 500 (logged)
"""
import logging

from flask import request, jsonify
from flask_login import login_required

from logistics import logistics_bp
from logistics.repositories.task_repository import TaskRepository
from .vehicles import _user_company_id

logger = logging.getLogger('jarvis.logistics')

_task_repo = TaskRepository()

# Query-string keys forwarded straight through to get_board()'s filters
# dict when present and non-empty. location_id is handled separately (needs
# int coercion); company_id is never taken from the client -- it always
# comes from current_user below (see _user_company_id).
_PASSTHROUGH_FILTER_KEYS = ('q', 'assignee')


@logistics_bp.route('/api/logistics/board', methods=['GET'])
@login_required
def get_board():
    """Kanban board — tasks grouped into the four fixed-order status
    columns (`De făcut` / `În lucru` / `Blocat` / `Finalizat`).

    Query params: q, location_id, assignee. company_id is never a query
    param here — it's always the caller's own company (see
    _user_company_id), so a request can't read another tenant's board by
    passing a different id.
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
        board = _task_repo.get_board(filters)
        return jsonify({'board': board}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(
            'Kanban board query failed (company_id=%r, filters=%r): %s',
            filters.get('company_id'), filters, e, exc_info=True,
        )
        return jsonify({'error': 'Internal error'}), 500
