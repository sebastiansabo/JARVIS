"""Repository for mkt_projects table."""

import json
import logging
import re
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.project_repo')


class ProjectRepository(BaseRepository):

    def get_by_id(self, project_id):
        return self.query_one('''
            SELECT p.*,
                   c.company as company_name,
                   b.name as brand_name,
                   u.name as owner_name, u.email as owner_email,
                   u2.name as created_by_name
            FROM mkt_projects p
            JOIN companies c ON c.id = p.company_id
            LEFT JOIN brands b ON b.id = p.brand_id
            JOIN users u ON u.id = p.owner_id
            JOIN users u2 ON u2.id = p.created_by
            WHERE p.id = %s AND p.deleted_at IS NULL
        ''', (project_id,))

    def list_projects(self, filters=None):
        filters = filters or {}
        where = ['p.deleted_at IS NULL']
        params = []

        if filters.get('status'):
            where.append('p.status = %s')
            params.append(filters['status'])
        if filters.get('company_id'):
            where.append('p.company_id = %s')
            params.append(int(filters['company_id']))
        if filters.get('brand_id'):
            where.append('p.brand_id = %s')
            params.append(int(filters['brand_id']))
        if filters.get('visible_to_user_id'):
            uid = int(filters['visible_to_user_id'])
            dept_cid = filters.get('department_company_id')
            user_clauses = [
                'p.owner_id = %s',
                'EXISTS (SELECT 1 FROM mkt_project_members m WHERE m.project_id = p.id AND m.user_id = %s)',
                '''EXISTS (
                    SELECT 1 FROM approval_requests ar
                    WHERE ar.entity_type = 'mkt_project' AND ar.entity_id = p.id
                      AND ar.status IN ('pending', 'on_hold')
                      AND ((ar.context_snapshot->>'approver_user_id')::int = %s
                           OR ar.context_snapshot->'stakeholder_approver_ids' @> to_jsonb(%s::int))
                )''',
            ]
            user_params = [uid, uid, uid, uid]
            if dept_cid:
                user_clauses.append('p.company_id = %s')
                user_params.append(int(dept_cid))
            where.append('(' + ' OR '.join(user_clauses) + ')')
            params.extend(user_params)
        elif filters.get('owner_id'):
            where.append('p.owner_id = %s')
            params.append(int(filters['owner_id']))
        if filters.get('project_type'):
            where.append('p.project_type = %s')
            params.append(filters['project_type'])
        if filters.get('date_from'):
            where.append('p.start_date >= %s')
            params.append(filters['date_from'])
        if filters.get('date_to'):
            where.append('p.end_date <= %s')
            params.append(filters['date_to'])
        if filters.get('search'):
            where.append('(p.name ILIKE %s OR p.description ILIKE %s)')
            term = f"%{filters['search']}%"
            params.extend([term, term])

        where_clause = ' AND '.join(where)
        limit = min(int(filters.get('limit', 100)), 500)
        offset = int(filters.get('offset', 0))

        def _work(cursor):
            cursor.execute(f'''
                SELECT p.*,
                       c.company as company_name,
                       b.name as brand_name,
                       u.name as owner_name,
                       (SELECT COALESCE(SUM(bl.spent_amount), 0) FROM mkt_budget_lines bl WHERE bl.project_id = p.id) as total_spent
                FROM mkt_projects p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN brands b ON b.id = p.brand_id
                JOIN users u ON u.id = p.owner_id
                WHERE {where_clause}
                ORDER BY p.updated_at DESC
                LIMIT %s OFFSET %s
            ''', params + [limit, offset])
            rows = cursor.fetchall()

            cursor.execute(f'''
                SELECT COUNT(*) as total
                FROM mkt_projects p
                WHERE {where_clause}
            ''', params)
            total = cursor.fetchone()['total']

            return {'projects': [dict(r) for r in rows], 'total': total}
        return self.execute_many(_work)

    def create(self, name, company_id, owner_id, created_by, **kwargs):
        def _work(cursor):
            slug = self._generate_slug(cursor, name)
            channel_mix = kwargs.get('channel_mix', [])
            if isinstance(channel_mix, list):
                channel_mix = '{' + ','.join(channel_mix) + '}'
            company_ids = kwargs.get('company_ids', [])
            if isinstance(company_ids, list):
                company_ids = '{' + ','.join(str(c) for c in company_ids) + '}'
            brand_ids = kwargs.get('brand_ids', [])
            if isinstance(brand_ids, list):
                brand_ids = '{' + ','.join(str(b) for b in brand_ids) + '}'
            department_ids = kwargs.get('department_ids', [])
            if isinstance(department_ids, list):
                department_ids = '{' + ','.join(str(d) for d in department_ids) + '}'

            cursor.execute('''
                INSERT INTO mkt_projects
                    (name, slug, description, company_id, company_ids, brand_id, brand_ids,
                     department_structure_id, department_ids,
                     project_type, channel_mix, status, start_date, end_date,
                     total_budget, currency, owner_id, created_by,
                     objective, target_audience, brief, external_ref, metadata,
                     approval_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                name, slug, kwargs.get('description'),
                company_id, company_ids, kwargs.get('brand_id'), brand_ids,
                kwargs.get('department_structure_id'), department_ids,
                kwargs.get('project_type', 'campaign'), channel_mix,
                kwargs.get('start_date'), kwargs.get('end_date'),
                kwargs.get('total_budget', 0), kwargs.get('currency', 'RON'),
                owner_id, created_by,
                kwargs.get('objective'), kwargs.get('target_audience'),
                json.dumps(kwargs.get('brief', {})),
                kwargs.get('external_ref'),
                json.dumps(kwargs.get('metadata', {})),
                kwargs.get('approval_mode', 'any'),
            ))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update(self, project_id, **kwargs):
        allowed = {
            'name', 'description', 'company_id', 'company_ids', 'brand_id', 'brand_ids',
            'department_structure_id', 'department_ids',
            'project_type', 'channel_mix', 'status', 'start_date', 'end_date',
            'total_budget', 'currency', 'owner_id', 'objective', 'target_audience',
            'brief', 'external_ref', 'metadata', 'approval_mode',
        }
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                if key == 'channel_mix' and isinstance(val, list):
                    val = '{' + ','.join(val) + '}'
                if key in ('company_ids', 'brand_ids', 'department_ids') and isinstance(val, list):
                    val = '{' + ','.join(str(v) for v in val) + '}'
                if key in ('brief', 'metadata') and isinstance(val, dict):
                    val = json.dumps(val)
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False
        updates.append('updated_at = NOW()')
        params.append(project_id)
        return self.execute(
            f'UPDATE mkt_projects SET {", ".join(updates)} WHERE id = %s AND deleted_at IS NULL',
            params
        ) > 0

    def soft_delete(self, project_id):
        return self.execute(
            'UPDATE mkt_projects SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
            (project_id,)
        ) > 0

    def update_status(self, project_id, status):
        return self.execute(
            'UPDATE mkt_projects SET status = %s, updated_at = NOW() WHERE id = %s AND deleted_at IS NULL',
            (status, project_id)
        ) > 0

    def archive(self, project_id):
        return self.execute(
            "UPDATE mkt_projects SET status = 'archived', updated_at = NOW() WHERE id = %s AND deleted_at IS NULL",
            (project_id,)
        ) > 0

    def restore(self, project_id):
        """Restore from archived status or from soft-delete (trash)."""
        return self.execute(
            "UPDATE mkt_projects SET status = 'draft', deleted_at = NULL, updated_at = NOW() WHERE id = %s",
            (project_id,)
        ) > 0

    def list_archived(self, limit=100, offset=0):
        def _work(cursor):
            cursor.execute('''
                SELECT p.*, c.company as company_name, b.name as brand_name, u.name as owner_name,
                       (SELECT COALESCE(SUM(bl.spent_amount), 0) FROM mkt_budget_lines bl WHERE bl.project_id = p.id) as total_spent
                FROM mkt_projects p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN brands b ON b.id = p.brand_id
                JOIN users u ON u.id = p.owner_id
                WHERE p.status = 'archived' AND p.deleted_at IS NULL
                ORDER BY p.updated_at DESC
                LIMIT %s OFFSET %s
            ''', (limit, offset))
            return [dict(r) for r in cursor.fetchall()]
        return self.execute_many(_work)

    def list_deleted(self, limit=100, offset=0):
        def _work(cursor):
            cursor.execute('''
                SELECT p.*, c.company as company_name, b.name as brand_name, u.name as owner_name,
                       (SELECT COALESCE(SUM(bl.spent_amount), 0) FROM mkt_budget_lines bl WHERE bl.project_id = p.id) as total_spent
                FROM mkt_projects p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN brands b ON b.id = p.brand_id
                JOIN users u ON u.id = p.owner_id
                WHERE p.deleted_at IS NOT NULL
                ORDER BY p.deleted_at DESC
                LIMIT %s OFFSET %s
            ''', (limit, offset))
            return [dict(r) for r in cursor.fetchall()]
        return self.execute_many(_work)

    def permanent_delete(self, project_id):
        """Hard delete — only for projects already in trash."""
        return self.execute(
            'DELETE FROM mkt_projects WHERE id = %s AND deleted_at IS NOT NULL',
            (project_id,)
        ) > 0

    def duplicate(self, project_id, new_name, created_by):
        """Clone a project as a new draft."""
        original = self.get_by_id(project_id)
        if not original:
            return None
        return self.create(
            name=new_name,
            company_id=original['company_id'],
            owner_id=created_by,
            created_by=created_by,
            description=original.get('description'),
            company_ids=original.get('company_ids', []),
            brand_id=original.get('brand_id'),
            brand_ids=original.get('brand_ids', []),
            department_structure_id=original.get('department_structure_id'),
            department_ids=original.get('department_ids', []),
            project_type=original.get('project_type', 'campaign'),
            channel_mix=original.get('channel_mix', []),
            total_budget=original.get('total_budget', 0),
            currency=original.get('currency', 'RON'),
            objective=original.get('objective'),
            target_audience=original.get('target_audience'),
            brief=original.get('brief', {}),
            approval_mode=original.get('approval_mode', 'any'),
        )

    def _generate_slug(self, cursor, name):
        base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:60]
        slug = base
        counter = 1
        while True:
            cursor.execute('SELECT 1 FROM mkt_projects WHERE slug = %s', (slug,))
            if not cursor.fetchone():
                return slug
            slug = f'{base}-{counter}'
            counter += 1
