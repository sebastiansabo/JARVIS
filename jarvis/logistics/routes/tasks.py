"""Kanban board routes — the browser-facing Panou de lucru API: the
read-only board (Task 7) plus the move action (Task 8's `POST .../move`).

Same surface as routes/vehicles.py (NOT jarvis-alpha's server-to-server
intake feed in routes/intake.py) — gated by `@login_required`, with the
acting company resolved from `current_user` via the shared
`_user_company_id()` helper (imported from vehicles.py — see that module's
docstring for the Phase-1 scope this rides on).

No SQL here (per repo convention) — every query/write goes through
`TaskRepository`/`logistics.services.moves.move_task`. Exception mapping
mirrors routes/vehicles.py's documented convention, extended with the two
move-specific cases:
  MoveError       -> 400 {error: <code>}  (a gate rejected the move)
  ValueError      -> 400
  PermissionError -> 403  (task belongs to another company)
  anything else   -> 500 (logged)
"""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from logistics import logistics_bp
from logistics.repositories.task_repository import BOARD_STATUSES, TaskRepository
from logistics.services.moves import MoveError, move_task
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


@logistics_bp.route('/api/logistics/tasks/<int:task_id>/move', methods=['POST'])
@login_required
def move_task_route(task_id):
    """Move a Kanban card to a new status. Body: `{to_status, block?}`
    where `block` (required only when `to_status == 'Blocat'`) is
    `{responsible, next_action}`.

    Cross-tenant write guard: the task's own company (via its vehicle) must
    match the caller's company (see `_user_company_id`) — a task from
    another tenant 403s rather than 404ing or silently succeeding, so a
    probing client can't distinguish "not yours" from "doesn't exist".
    """
    body = request.get_json(silent=True) or {}
    to_status = body.get('to_status')
    if not isinstance(to_status, str) or not to_status:
        return jsonify({'error': 'to_status is required'}), 400
    # The status column has no DB-level CHECK constraint, and get_board()
    # silently drops any row whose status isn't one of the four columns --
    # reject an unrecognized target here instead of letting a typo'd/
    # malicious value make the card vanish from the board.
    if to_status not in BOARD_STATUSES:
        return jsonify({'error': f'to_status must be one of {BOARD_STATUSES}'}), 400

    task = _task_repo.get_task_by_id(task_id)
    if task is None:
        return jsonify({'error': f'task {task_id} not found'}), 400
    caller_company_id = _user_company_id()
    # Fail closed: a caller with no company (company_id is None) must never
    # match a task whose own company_id happens to also be None (`None ==
    # None` is True in Python, unlike the `company_id = %s` SQL filter the
    # read routes use, where a NULL param matches no row) — require a real,
    # equal company_id on both sides.
    if caller_company_id is None or task.get('company_id') != caller_company_id:
        return jsonify({'error': 'Forbidden'}), 403

    ctx = {
        'block': body.get('block'),
        'actor': getattr(current_user, 'name', None) or getattr(current_user, 'email', None),
    }

    try:
        updated = move_task(task_id, to_status, ctx)
        return jsonify({'task': updated}), 200
    except MoveError as e:
        return jsonify({'error': e.code}), 400
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except PermissionError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(
            'Task move failed (task_id=%r, to_status=%r): %s',
            task_id, to_status, e, exc_info=True,
        )
        return jsonify({'error': 'Internal error'}), 500
