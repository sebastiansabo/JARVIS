"""History Repository — Data access for logistics_vehicle_history (audit
trail; one row per vehicle state change, written on every Kanban move per
§4.2 of the design spec).
"""
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from core.base_repository import BaseRepository


def _adapt_jsonb(value: Any) -> Any:
    """old/new are JSONB — wrap dict/list values in Json() so psycopg2 can
    adapt them. Strings and None pass through unchanged."""
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


class HistoryRepository(BaseRepository):
    """Data access for logistics_vehicle_history."""

    def record_history(self, vehicle_id: int, event_type: str, old: Any, new: Any,
                        actor: str, company_id: int = None) -> Dict[str, Any]:
        """Insert one audit-trail row for a vehicle state change. Returns the
        created record."""
        return self.execute(
            '''
            INSERT INTO logistics_vehicle_history
                (vehicle_id, event_type, old_value, new_value, actor, company_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            ''',
            (vehicle_id, event_type, _adapt_jsonb(old), _adapt_jsonb(new), actor, company_id),
            returning=True,
        )

    def get_history_by_id(self, history_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('SELECT * FROM logistics_vehicle_history WHERE id = %s', (history_id,))

    def list_history_for_vehicle(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Full audit trail for a vehicle, newest first (the Fișa mașinii
        timeline — a later task's read path)."""
        return self.query_all(
            'SELECT * FROM logistics_vehicle_history WHERE vehicle_id = %s ORDER BY created_at DESC',
            (vehicle_id,),
        )
