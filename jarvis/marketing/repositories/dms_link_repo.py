"""Repository for mkt_project_dms_links — links DMS documents to marketing projects."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.dms_link_repo')


class ProjectDmsLinkRepository(BaseRepository):

    def get_by_project(self, project_id):
        """Get all linked DMS documents for a project."""
        return self.query_all('''
            SELECT l.id, l.project_id, l.document_id, l.linked_by,
                   u.name as linked_by_name, l.created_at,
                   d.title, d.description, d.status,
                   d.doc_number, d.doc_date, d.expiry_date,
                   d.category_id, c.name as category_name, c.color as category_color,
                   d.signature_status, d.company_id,
                   comp.company as company_name,
                   d.created_by, cb.name as created_by_name,
                   d.created_at as doc_created_at,
                   d.visibility,
                   (SELECT COUNT(*) FROM dms_files df WHERE df.document_id = d.id) as file_count,
                   (SELECT COUNT(*) FROM dms_documents ch
                    WHERE ch.parent_id = d.id AND ch.deleted_at IS NULL) as children_count,
                   CASE WHEN d.expiry_date IS NOT NULL
                        THEN (d.expiry_date::date - CURRENT_DATE)::integer
                        ELSE NULL END as days_to_expiry
            FROM mkt_project_dms_links l
            JOIN dms_documents d ON d.id = l.document_id
            JOIN users u ON u.id = l.linked_by
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies comp ON comp.id = d.company_id
            LEFT JOIN users cb ON cb.id = d.created_by
            WHERE l.project_id = %s AND d.deleted_at IS NULL
            ORDER BY l.created_at DESC
        ''', (project_id,))

    def link(self, project_id, document_id, linked_by):
        """Link a DMS document to a project. Returns link ID or None if already linked."""
        row = self.execute('''
            INSERT INTO mkt_project_dms_links (project_id, document_id, linked_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (project_id, document_id) DO NOTHING
            RETURNING id
        ''', (project_id, document_id, linked_by), returning=True)
        return row['id'] if row else None

    def unlink(self, project_id, document_id):
        """Remove a DMS document link from a project."""
        return self.execute(
            'DELETE FROM mkt_project_dms_links WHERE project_id = %s AND document_id = %s',
            (project_id, document_id),
        ) > 0

    def search_documents(self, query=None, limit=20):
        """Search DMS documents for the linking picker."""
        sql = '''
            SELECT d.id, d.title, d.status, d.doc_number, d.doc_date,
                   d.expiry_date, c.name as category_name, c.color as category_color,
                   (SELECT COUNT(*) FROM dms_files df WHERE df.document_id = d.id) as file_count
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            WHERE d.deleted_at IS NULL AND d.parent_id IS NULL
        '''
        params = []
        if query:
            sql += " AND (d.title ILIKE %s OR d.doc_number ILIKE %s)"
            like = f'%{query}%'
            params.extend([like, like])
        sql += ' ORDER BY d.created_at DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, params)
