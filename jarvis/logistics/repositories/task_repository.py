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
