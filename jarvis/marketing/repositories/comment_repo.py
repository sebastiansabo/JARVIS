"""Repository for mkt_project_comments table."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.comment_repo')


class CommentRepository(BaseRepository):

    def get_by_project(self, project_id, include_internal=False):
        internal_filter = '' if include_internal else 'AND c.is_internal = FALSE'
        return self.query_all(f'''
            SELECT c.*, u.name as user_name, u.email as user_email
            FROM mkt_project_comments c
            JOIN users u ON u.id = c.user_id
            WHERE c.project_id = %s AND c.deleted_at IS NULL {internal_filter}
            ORDER BY c.created_at ASC
        ''', (project_id,))

    def create(self, project_id, user_id, content, parent_id=None, is_internal=False):
        row = self.execute('''
            INSERT INTO mkt_project_comments (project_id, user_id, content, parent_id, is_internal)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (project_id, user_id, content, parent_id, is_internal), returning=True)
        return row['id'] if row else None

    def update(self, comment_id, content):
        return self.execute(
            'UPDATE mkt_project_comments SET content = %s, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
            (content, comment_id)
        ) > 0

    def soft_delete(self, comment_id):
        return self.execute(
            'UPDATE mkt_project_comments SET deleted_at = NOW() WHERE id = %s',
            (comment_id,)
        ) > 0
