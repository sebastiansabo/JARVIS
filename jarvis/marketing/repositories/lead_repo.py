"""Repository for mkt_project_leads — the per-project lead sheet.

Leads are owned by a project (no CRM write on intake). ``create`` takes a
normalized payload from marketing.services.lead_intake.
"""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.lead_repo')

# Columns written from a normalized payload (see lead_intake.KNOWN_FIELDS + phone_raw).
_PAYLOAD_COLS = (
    'contact_name', 'phone', 'phone_raw', 'email', 'company_name', 'cui',
    'source', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'message', 'model_of_interest',
)

# Sentinel so update() can distinguish "leave unchanged" from "set to NULL".
_UNSET = object()


class ProjectLeadRepository(BaseRepository):

    def create(self, project_id, payload, received_via='webhook', webhook_id=None,
               external_id=None, assigned_to=None):
        """Insert a lead row from a normalized payload. Returns the new id."""
        cols = ['project_id', *_PAYLOAD_COLS, 'raw_payload', 'received_via',
                'webhook_id', 'external_id', 'assigned_to']
        values = [project_id]
        values += [payload.get(col) for col in _PAYLOAD_COLS]
        values += [json.dumps(payload.get('raw_payload') or {}), received_via,
                   webhook_id, external_id, assigned_to]
        placeholders = ', '.join(['%s'] * len(cols))
        row = self.execute(
            f'INSERT INTO mkt_project_leads ({", ".join(cols)}) '
            f'VALUES ({placeholders}) RETURNING id',
            values, returning=True,
        )
        return row['id'] if row else None

    def list_by_project(self, project_id, status=None, search=None,
                        assigned_to=None, limit=100, offset=0):
        """List leads for a project, newest first, with optional filters.

        assigned_to: a user id to filter by, or the string 'unassigned' for
        leads with no assignee.
        """
        sql = ('SELECT l.*, u.name AS assigned_to_name '
               'FROM mkt_project_leads l '
               'LEFT JOIN users u ON u.id = l.assigned_to '
               'WHERE l.project_id = %s')
        params = [project_id]
        if status:
            sql += ' AND l.status = %s'
            params.append(status)
        if assigned_to == 'unassigned':
            sql += ' AND l.assigned_to IS NULL'
        elif assigned_to is not None:
            sql += ' AND l.assigned_to = %s'
            params.append(assigned_to)
        if search:
            sql += (' AND (l.contact_name ILIKE %s OR l.phone ILIKE %s '
                    'OR l.email ILIKE %s OR l.company_name ILIKE %s)')
            like = f'%{search}%'
            params.extend([like, like, like, like])
        sql += ' ORDER BY l.created_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        return self.query_all(sql, params)

    def status_counts(self, project_id):
        """Return {status: count} for a project's leads (drives filter-chip badges)."""
        rows = self.query_all(
            'SELECT status, COUNT(*) AS cnt FROM mkt_project_leads '
            'WHERE project_id = %s GROUP BY status',
            (project_id,),
        )
        return {r['status']: r['cnt'] for r in rows}

    def get_by_external_id(self, project_id, external_id):
        """Find a lead by its client-supplied idempotency id, or None."""
        return self.query_one(
            'SELECT * FROM mkt_project_leads WHERE project_id = %s AND external_id = %s',
            (project_id, external_id),
        )

    def find_recent_duplicate(self, project_id, phone=None, email=None, within_minutes=10):
        """Most recent lead in this project matching phone OR email within the
        time window — used to absorb webhook retries. None when no identity."""
        idents, params = [], [project_id]
        if phone:
            idents.append('phone = %s')
            params.append(phone)
        if email:
            idents.append('email = %s')
            params.append(email)
        if not idents:
            return None
        params.append(within_minutes)
        return self.query_one(
            f'SELECT * FROM mkt_project_leads '
            f'WHERE project_id = %s AND ({" OR ".join(idents)}) '
            f'AND created_at >= (CURRENT_TIMESTAMP - make_interval(mins => %s)) '
            f'ORDER BY created_at DESC LIMIT 1',
            params,
        )

    def update(self, project_id, lead_id, status=None, status_notes=None, assigned_to=_UNSET):
        """Update a lead's status/notes/assignee. Scoped by project_id.

        assigned_to: pass a user id to assign, None to unassign, or omit to
        leave unchanged.
        """
        fields, params = [], []
        if status is not None:
            fields.append('status = %s')
            params.append(status)
        if status_notes is not None:
            fields.append('status_notes = %s')
            params.append(status_notes)
        if assigned_to is not _UNSET:
            fields.append('assigned_to = %s')
            params.append(assigned_to)
        if not fields:
            return False
        fields.append('updated_at = CURRENT_TIMESTAMP')
        params.extend([lead_id, project_id])
        return self.execute(
            f'UPDATE mkt_project_leads SET {", ".join(fields)} '
            f'WHERE id = %s AND project_id = %s',
            params,
        ) > 0

    def mark_converted(self, project_id, lead_id, client_id, user_id):
        """Flag a lead converted and record which CRM client it became."""
        return self.execute(
            "UPDATE mkt_project_leads "
            "SET status = 'converted', converted_client_id = %s, "
            "    converted_at = CURRENT_TIMESTAMP, converted_by = %s, "
            "    updated_at = CURRENT_TIMESTAMP "
            "WHERE id = %s AND project_id = %s",
            (client_id, user_id, lead_id, project_id),
        ) > 0

    def delete(self, project_id, lead_id):
        """Delete a lead. Scoped by project_id (no cross-project delete)."""
        return self.execute(
            'DELETE FROM mkt_project_leads WHERE id = %s AND project_id = %s',
            (lead_id, project_id),
        ) > 0

    def get_for_project(self, project_id, lead_id):
        """Fetch a single lead within a project (for convert), or None."""
        return self.query_one(
            'SELECT * FROM mkt_project_leads WHERE id = %s AND project_id = %s',
            (lead_id, project_id),
        )
