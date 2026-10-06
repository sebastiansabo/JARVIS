"""Repository for mkt_project_leads — the per-project lead sheet.

Leads are owned by a project (no CRM write). ``create`` takes a normalized
payload from marketing.services.lead_intake.
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


class ProjectLeadRepository(BaseRepository):

    def create(self, project_id, payload, received_via='webhook', webhook_id=None):
        """Insert a lead row from a normalized payload. Returns the new id."""
        cols = ['project_id', *_PAYLOAD_COLS, 'raw_payload', 'received_via', 'webhook_id']
        values = [project_id]
        values += [payload.get(col) for col in _PAYLOAD_COLS]
        values += [json.dumps(payload.get('raw_payload') or {}), received_via, webhook_id]
        placeholders = ', '.join(['%s'] * len(cols))
        row = self.execute(
            f'INSERT INTO mkt_project_leads ({", ".join(cols)}) '
            f'VALUES ({placeholders}) RETURNING id',
            values, returning=True,
        )
        return row['id'] if row else None

    def list_by_project(self, project_id, status=None, search=None, limit=100, offset=0):
        """List leads for a project, newest first, with optional status/search filters."""
        sql = 'SELECT * FROM mkt_project_leads WHERE project_id = %s'
        params = [project_id]
        if status:
            sql += ' AND status = %s'
            params.append(status)
        if search:
            sql += (' AND (contact_name ILIKE %s OR phone ILIKE %s '
                    'OR email ILIKE %s OR company_name ILIKE %s)')
            like = f'%{search}%'
            params.extend([like, like, like, like])
        sql += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
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

    def update(self, project_id, lead_id, status=None, status_notes=None):
        """Update a lead's status/notes. Scoped by project_id (no cross-project edit)."""
        fields, params = [], []
        if status is not None:
            fields.append('status = %s')
            params.append(status)
        if status_notes is not None:
            fields.append('status_notes = %s')
            params.append(status_notes)
        if not fields:
            return False
        fields.append('updated_at = CURRENT_TIMESTAMP')
        params.extend([lead_id, project_id])
        return self.execute(
            f'UPDATE mkt_project_leads SET {", ".join(fields)} '
            f'WHERE id = %s AND project_id = %s',
            params,
        ) > 0

    def delete(self, project_id, lead_id):
        """Delete a lead. Scoped by project_id (no cross-project delete)."""
        return self.execute(
            'DELETE FROM mkt_project_leads WHERE id = %s AND project_id = %s',
            (lead_id, project_id),
        ) > 0
