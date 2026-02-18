"""Repository for mkt_project_events — links HR events to marketing projects."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.event_repo')


class ProjectEventRepository(BaseRepository):

    def get_by_project(self, project_id):
        """Get all linked HR events for a project."""
        return self.query_all('''
            SELECT pe.id, pe.project_id, pe.event_id, pe.notes,
                   pe.linked_by, u.name as linked_by_name, pe.created_at,
                   e.name as event_name, e.start_date as event_start_date,
                   e.end_date as event_end_date, e.company as event_company,
                   e.brand as event_brand, e.description as event_description
            FROM mkt_project_events pe
            JOIN hr.events e ON e.id = pe.event_id
            JOIN users u ON u.id = pe.linked_by
            WHERE pe.project_id = %s
            ORDER BY e.start_date DESC
        ''', (project_id,))

    def link(self, project_id, event_id, linked_by, notes=None):
        """Link an HR event to a project. Returns link ID or None if already linked."""
        # ON CONFLICT DO NOTHING may return no row
        row = self.execute('''
            INSERT INTO mkt_project_events (project_id, event_id, linked_by, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id, event_id) DO NOTHING
            RETURNING id
        ''', (project_id, event_id, linked_by, notes), returning=True)
        return row['id'] if row else None

    def unlink(self, project_id, event_id):
        """Remove an HR event link from a project."""
        return self.execute(
            'DELETE FROM mkt_project_events WHERE project_id = %s AND event_id = %s',
            (project_id, event_id),
        ) > 0

    def search_hr_events(self, query=None, limit=20):
        """Search HR events for the linking picker."""
        sql = '''
            SELECT e.id, e.name, e.start_date, e.end_date,
                   e.company, e.brand, e.description
            FROM hr.events e
        '''
        params = []
        if query:
            sql += " WHERE e.name ILIKE %s OR e.company ILIKE %s OR e.description ILIKE %s"
            like = f'%{query}%'
            params.extend([like, like, like])
        sql += ' ORDER BY e.start_date DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, params)
