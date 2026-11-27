"""Task Repository — Data access for logistics_tasks (Kanban cards).

Mirrors carpark/repositories/vehicle_repository.py's style: BaseRepository
for connection handling, a server-field-safe whitelist for create/update.
"""
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from core.base_repository import BaseRepository

# JSONB columns on logistics_tasks.
TASK_JSONB_FIELDS = {'measured_result'}

# Fields a caller may set via create_task()/update_task() (whitelist).
TASK_FIELDS = {
    'vehicle_id', 'action', 'type', 'location_id', 'position_id',
    'assignee', 'due_at', 'status', 'block_reason', 'block_next_action',
    'measured_result', 'source_event_id', 'company_id',
}

# Kanban status that means "this task is done" — used by
# get_open_reception_task() to find the still-open Recepție card for a
# vehicle (the one an ETA-update event must update in place, not duplicate).
_FINALIZAT = 'Finalizat'

# Kanban board (Task 7) — the four status columns, in the FIXED display
# order the design spec (§4.2) mandates: `De făcut` · `În lucru` · `Blocat` ·
# `Finalizat`. get_board() always returns exactly these keys, in exactly
# this order, even when a column has zero cards.
BOARD_STATUSES = ['De făcut', 'În lucru', 'Blocat', 'Finalizat']


def _adapt_jsonb(column: str, value: Any) -> Any:
    if column in TASK_JSONB_FIELDS and isinstance(value, (dict, list)):
        return Json(value)
    return value


class TaskRepository(BaseRepository):
    """Data access for logistics_tasks."""

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new task. Returns the created record."""
        safe_data = {k: v for k, v in data.items() if k in TASK_FIELDS}
        if not safe_data.get('vehicle_id'):
            raise ValueError('vehicle_id is required')
        if not safe_data.get('action'):
            raise ValueError('action is required')
        if not safe_data.get('type'):
            raise ValueError('type is required')

        columns = list(safe_data.keys())
        placeholders = ', '.join(['%s'] * len(columns))
        col_names = ', '.join(columns)
        values = [_adapt_jsonb(c, safe_data[c]) for c in columns]

        return self.execute(
            f'INSERT INTO logistics_tasks ({col_names}) VALUES ({placeholders}) RETURNING *',
            tuple(values), returning=True
        )

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('SELECT * FROM logistics_tasks WHERE id = %s', (task_id,))

    def get_open_reception_task(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """The vehicle's still-open (not Finalizat) Recepție task, or None.

        Used by the intake pipeline (Task 2) to find the same card an
        `ETA actualizat` event should update in place, instead of creating a
        second one — the "ETA update: same card's due time, no second card"
        acceptance test (§2.2 of the design spec).
        """
        return self.query_one(
            '''
            SELECT * FROM logistics_tasks
            WHERE vehicle_id = %s AND type = 'Recepție' AND status != %s
            ORDER BY created_at ASC
            LIMIT 1
            ''',
            (vehicle_id, _FINALIZAT),
        )

    def update_task(self, task_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update task fields. Returns the updated record (or the unchanged
        current record if patch has no whitelisted fields)."""
        safe_data = {k: v for k, v in patch.items() if k in TASK_FIELDS}
        if not safe_data:
            return self.get_task_by_id(task_id)

        sets = []
        params = []
        for key, value in safe_data.items():
            sets.append(f'{key} = %s')
            params.append(_adapt_jsonb(key, value))
        sets.append('updated_at = CURRENT_TIMESTAMP')

        params.append(task_id)
        return self.execute(
            f"UPDATE logistics_tasks SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def get_board(self, filters: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Kanban board (Panou de lucru) — tasks grouped into the four
        fixed-order status columns (BOARD_STATUSES).

        `filters` (all optional except `company_id`):
          q            — free-text search against the vehicle's model /
                         order_ref (NOT the task's own fields)
          location_id  — exact match on the vehicle's current location
                         (logistics_vehicles.location_id)
          assignee     — exact match on logistics_tasks.assignee
          company_id   — tenant scope (every query is scoped by this, on
                         the task row itself -- mirrors list_tasks())

        Each card dict has exactly 9 keys: id, title, type, vehicle_model,
        order_ref, location_name, position_code, assignee, due_at.
        `title` is the task's `action` column; `location_name`/
        `position_code` come from the VEHICLE's current location/bay (joined
        tasks -> vehicles -> locations/positions) -- not the task's own
        (currently-unused) location_id/position_id columns, since the
        reception flow (Task 9) writes a confirmed location onto the
        vehicle, not the task.

        Columns are always present in the returned dict, even empty (a
        filter that matches nothing in a column still yields `[]`, never a
        missing key) -- callers can iterate BOARD_STATUSES without a
        membership check.

        Cards within a column are ordered by creation (oldest first), tied
        broken by id, so the ordering is stable across calls.
        """
        where = ['t.company_id = %s']
        params: list = [filters.get('company_id')]

        q = filters.get('q')
        if q:
            like = f'%{q}%'
            where.append("(COALESCE(v.model, '') ILIKE %s OR v.order_ref ILIKE %s)")
            params.extend([like, like])

        location_id = filters.get('location_id')
        if location_id is not None:
            where.append('v.location_id = %s')
            params.append(location_id)

        assignee = filters.get('assignee')
        if assignee:
            where.append('t.assignee = %s')
            params.append(assignee)

        sql = f'''
            SELECT
                t.id, t.action AS title, t.type, t.status,
                v.model AS vehicle_model, v.order_ref,
                l.name AS location_name, p.code AS position_code,
                t.assignee, t.due_at
            FROM logistics_tasks t
            JOIN logistics_vehicles v ON t.vehicle_id = v.id
            LEFT JOIN logistics_locations l ON v.location_id = l.id
            LEFT JOIN logistics_positions p ON v.position_id = p.id
            WHERE {' AND '.join(where)}
            ORDER BY t.created_at ASC, t.id ASC
        '''
        rows = self.query_all(sql, tuple(params))

        board: Dict[str, List[Dict[str, Any]]] = {status: [] for status in BOARD_STATUSES}
        for row in rows:
            status = row.pop('status', None)
            if status in board:
                board[status].append(row)
            # else: a task status outside BOARD_STATUSES (shouldn't happen —
            # the schema default/callers only ever write the 4 known values)
            # is dropped rather than crashing the whole board.
        return board

    def list_tasks(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """List tasks matching filters: company_id, vehicle_id, status, type,
        location_id, assignee. All optional; no filters returns every task."""
        filters = filters or {}
        where_clauses = []
        params: list = []

        for column in ('company_id', 'vehicle_id', 'status', 'type', 'location_id', 'assignee'):
            if filters.get(column) is not None:
                where_clauses.append(f'{column} = %s')
                params.append(filters[column])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
        return self.query_all(
            f'SELECT * FROM logistics_tasks {where_sql} ORDER BY created_at DESC',
            tuple(params),
        )
