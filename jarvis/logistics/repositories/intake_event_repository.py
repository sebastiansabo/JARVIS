"""Intake Event Repository — Data access for logistics_intake_events (the raw
jarvis-alpha event log; every event received at
`POST /api/logistics/intake/events` gets one row here, per §3 of the design
spec).

Named `IntakeEventRepository` (not `EventRepository`) — the modularity hook
reserves `EventRepository`/`DocumentRepository`/`PhotoRepository` for
carpark.
"""
from typing import Any, Dict, List

from psycopg2.extras import Json

from core.base_repository import BaseRepository


class IntakeEventRepository(BaseRepository):
    """Data access for logistics_intake_events."""

    def log(self, order_ref: str, code: str, payload: Dict[str, Any], event_ts: int,
            result: str, company_id: int = None) -> Dict[str, Any]:
        """Insert one intake event log row. Returns the created record.

        `result` records what the intake pipeline (Task 2) did with this
        event: created / updated / ignored-stale / duplicate.
        """
        return self.execute(
            '''
            INSERT INTO logistics_intake_events (order_ref, code, payload, event_ts, result, company_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            ''',
            (order_ref, code, Json(payload or {}), event_ts, result, company_id),
            returning=True,
        )

    def list_for_order(self, order_ref: str) -> List[Dict[str, Any]]:
        """Full event history for one order, oldest first (ordering-guard
        debugging / the Sincronizare panel's event log, §4.5)."""
        return self.query_all(
            'SELECT * FROM logistics_intake_events WHERE order_ref = %s ORDER BY event_ts ASC',
            (order_ref,),
        )
