"""Repository for mkt_project_activity table."""

import json
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.activity_repo')


class ActivityRepository(BaseRepository):

    def get_by_project(self, project_id, limit=50, offset=0):
        return self.query_all('''
            SELECT a.*, u.name as actor_name
            FROM mkt_project_activity a
            LEFT JOIN users u ON u.id = a.actor_id
            WHERE a.project_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s OFFSET %s
        ''', (project_id, limit, offset))

    def log(self, project_id, action, actor_id=None, actor_type='user', details=None):
        row = self.execute('''
            INSERT INTO mkt_project_activity (project_id, action, actor_id, actor_type, details)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (project_id, action, actor_id, actor_type, json.dumps(details or {})),
            returning=True)
        return row['id'] if row else None
