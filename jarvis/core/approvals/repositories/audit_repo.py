"""Repository for approval_audit_log table. Append-only."""

import json
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.approvals.audit_repo')


class AuditRepository(BaseRepository):

    def log(self, request_id, action, actor_id=None, actor_type='user', details=None):
        """Append an entry to the audit log."""
        row = self.execute('''
            INSERT INTO approval_audit_log (request_id, action, actor_id, actor_type, details)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id
        ''', (
            request_id, action, actor_id, actor_type,
            json.dumps(details) if details else '{}',
        ), returning=True)
        return row['id'] if row else None

    def get_for_request(self, request_id):
        return self.query_all('''
            SELECT al.*,
                   u.name as actor_name, u.email as actor_email
            FROM approval_audit_log al
            LEFT JOIN users u ON u.id = al.actor_id
            WHERE al.request_id = %s
            ORDER BY al.created_at
        ''', (request_id,))

    def get_global(self, limit=100, offset=0, action=None, actor_id=None):
        """Global audit log with optional filters."""
        wheres = []
        params = []
        if action:
            wheres.append('al.action = %s')
            params.append(action)
        if actor_id:
            wheres.append('al.actor_id = %s')
            params.append(actor_id)
        where_clause = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
        params.extend([limit, offset])
        return self.query_all(f'''
            SELECT al.*,
                   u.name as actor_name,
                   r.entity_type, r.entity_id
            FROM approval_audit_log al
            LEFT JOIN users u ON u.id = al.actor_id
            LEFT JOIN approval_requests r ON r.id = al.request_id
            {where_clause}
            ORDER BY al.created_at DESC
            LIMIT %s OFFSET %s
        ''', params)
