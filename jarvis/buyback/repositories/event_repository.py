"""Data access for buyback_events — append-only audit log of actions taken on
a buyback_records row (status changes, edits, offer decisions, ...).

JSONB idiom: `details` is a JSONB column. psycopg2 cannot adapt a raw Python
dict directly (raises "can't adapt type 'dict'"), so a dict must be wrapped in
psycopg2.extras.Json() before binding. This mirrors the idiom used by
ai_agent/repositories/rag_document_repository.py (`Json(x) if x else None`) —
None passes straight through as a real SQL NULL rather than being coerced
into an empty-object JSONB value.

On read, BaseRepository's query_one/query_all use RealDictCursor, and
psycopg2 auto-deserializes JSONB columns back into Python dicts, so
row['details']['key'] works directly with no extra parsing here.
"""

from psycopg2.extras import Json

from core.base_repository import BaseRepository


class EventRepository(BaseRepository):

    def log(self, record_id, action, actor, details=None) -> dict:
        """Append one audit event for `record_id`. `details` is an optional
        dict, wrapped in Json() so psycopg2 serializes it into the JSONB
        column; None is passed through as-is (stored as SQL NULL)."""
        sql = (
            'INSERT INTO buyback_events (record_id, action, actor, details) '
            'VALUES (%s, %s, %s, %s) RETURNING *'
        )
        params = (record_id, action, actor, Json(details) if details else None)
        return self.execute(sql, params, returning=True)

    def list_for_record(self, record_id) -> list:
        """All audit events for `record_id`, newest first."""
        sql = (
            'SELECT * FROM buyback_events WHERE record_id = %s '
            'ORDER BY created_at DESC, id DESC'
        )
        return self.query_all(sql, (record_id,))
