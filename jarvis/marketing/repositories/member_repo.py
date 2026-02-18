"""Repository for mkt_project_members table."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.member_repo')


class MemberRepository(BaseRepository):

    def get_by_project(self, project_id):
        return self.query_all('''
            SELECT m.*, u.name as user_name, u.email as user_email,
                   u2.name as added_by_name
            FROM mkt_project_members m
            JOIN users u ON u.id = m.user_id
            JOIN users u2 ON u2.id = m.added_by
            WHERE m.project_id = %s
            ORDER BY m.created_at
        ''', (project_id,))

    def add(self, project_id, user_id, role, added_by, department_structure_id=None):
        # ON CONFLICT DO UPDATE always returns a row
        row = self.execute('''
            INSERT INTO mkt_project_members (project_id, user_id, role, added_by, department_structure_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role
            RETURNING id
        ''', (project_id, user_id, role, added_by, department_structure_id), returning=True)
        return row['id'] if row else None

    def update_role(self, member_id, role):
        return self.execute(
            'UPDATE mkt_project_members SET role = %s WHERE id = %s',
            (role, member_id)
        ) > 0

    def remove(self, member_id):
        return self.execute(
            'DELETE FROM mkt_project_members WHERE id = %s', (member_id,)
        ) > 0

    def get_user_ids_for_project(self, project_id):
        rows = self.query_all(
            'SELECT user_id FROM mkt_project_members WHERE project_id = %s',
            (project_id,)
        )
        return [r['user_id'] for r in rows]

    def get_stakeholder_ids(self, project_id):
        """Get user IDs of all stakeholders for a project."""
        rows = self.query_all(
            'SELECT user_id FROM mkt_project_members WHERE project_id = %s AND role = %s',
            (project_id, 'stakeholder')
        )
        return [r['user_id'] for r in rows]

    def is_member(self, project_id, user_id):
        return self.query_one(
            'SELECT 1 FROM mkt_project_members WHERE project_id = %s AND user_id = %s',
            (project_id, user_id)
        ) is not None
