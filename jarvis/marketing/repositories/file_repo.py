"""Repository for mkt_project_files table."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.file_repo')


class MarketingFileRepository(BaseRepository):

    def get_by_project(self, project_id):
        return self.query_all('''
            SELECT f.*, u.name as uploaded_by_name
            FROM mkt_project_files f
            JOIN users u ON u.id = f.uploaded_by
            WHERE f.project_id = %s
            ORDER BY f.category NULLS LAST, f.created_at DESC
        ''', (project_id,))

    def create(self, project_id, file_name, storage_uri, uploaded_by, **kwargs):
        row = self.execute('''
            INSERT INTO mkt_project_files
                (project_id, file_name, file_type, mime_type, file_size, storage_uri, uploaded_by, description, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            project_id, file_name,
            kwargs.get('file_type'), kwargs.get('mime_type'),
            kwargs.get('file_size'), storage_uri, uploaded_by,
            kwargs.get('description'), kwargs.get('category'),
        ), returning=True)
        return row['id'] if row else None

    def update(self, file_id, **kwargs):
        sets = []
        params = []
        for col in ('category', 'description'):
            if col in kwargs:
                sets.append(f'{col} = %s')
                params.append(kwargs[col])
        if not sets:
            return False
        params.append(file_id)
        return self.execute(
            f'UPDATE mkt_project_files SET {", ".join(sets)} WHERE id = %s',
            tuple(params),
        ) > 0

    def get_categories(self, project_id):
        rows = self.query_all('''
            SELECT DISTINCT category FROM mkt_project_files
            WHERE project_id = %s AND category IS NOT NULL
            ORDER BY category
        ''', (project_id,))
        return [r['category'] for r in rows]

    def delete(self, file_id):
        return self.execute(
            'DELETE FROM mkt_project_files WHERE id = %s', (file_id,)
        ) > 0
