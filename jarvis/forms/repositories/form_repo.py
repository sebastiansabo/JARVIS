"""Repository for forms table."""

import json
import logging
import re
from core.base_repository import BaseRepository
from database import dict_from_row

logger = logging.getLogger('jarvis.forms.form_repo')


class FormRepository(BaseRepository):

    def get_by_id(self, form_id):
        """Get form by ID with company name, owner name, and submission count."""
        return self.query_one('''
            SELECT f.*,
                   c.company as company_name,
                   u.name as owner_name,
                   u2.name as created_by_name,
                   (SELECT COUNT(*) FROM form_submissions fs
                    WHERE fs.form_id = f.id) as submission_count
            FROM forms f
            JOIN companies c ON c.id = f.company_id
            JOIN users u ON u.id = f.owner_id
            JOIN users u2 ON u2.id = f.created_by
            WHERE f.id = %s AND f.deleted_at IS NULL
        ''', (form_id,))

    def get_by_slug(self, slug):
        """Get published form by slug (for public access)."""
        return self.query_one('''
            SELECT f.id, f.name, f.slug, f.description,
                   f.published_schema, f.settings, f.utm_config, f.branding,
                   f.version, f.company_id, f.requires_approval,
                   c.company as company_name
            FROM forms f
            JOIN companies c ON c.id = f.company_id
            WHERE f.slug = %s
              AND f.status = 'published'
              AND f.deleted_at IS NULL
              AND f.published_schema IS NOT NULL
        ''', (slug,))

    def list_forms(self, filters=None):
        """List forms with pagination and filtering."""
        filters = filters or {}
        where = ['f.deleted_at IS NULL']
        params = []

        if filters.get('status'):
            where.append('f.status = %s')
            params.append(filters['status'])
        if filters.get('company_id'):
            where.append('f.company_id = %s')
            params.append(int(filters['company_id']))
        if filters.get('owner_id'):
            where.append('f.owner_id = %s')
            params.append(int(filters['owner_id']))
        if filters.get('search'):
            where.append('(f.name ILIKE %s OR f.description ILIKE %s)')
            term = f"%{filters['search']}%"
            params.extend([term, term])

        where_clause = ' AND '.join(where)
        limit = min(int(filters.get('limit', 100)), 500)
        offset = int(filters.get('offset', 0))

        def _work(cursor):
            cursor.execute(f'''
                SELECT f.*,
                       c.company as company_name,
                       u.name as owner_name,
                       (SELECT COUNT(*) FROM form_submissions fs
                        WHERE fs.form_id = f.id) as submission_count
                FROM forms f
                JOIN companies c ON c.id = f.company_id
                JOIN users u ON u.id = f.owner_id
                WHERE {where_clause}
                ORDER BY f.updated_at DESC
                LIMIT %s OFFSET %s
            ''', params + [limit, offset])
            rows = cursor.fetchall()

            cursor.execute(f'''
                SELECT COUNT(*) as total
                FROM forms f
                WHERE {where_clause}
            ''', params)
            total = cursor.fetchone()['total']

            return {'forms': [dict_from_row(r) for r in rows], 'total': total}
        return self.execute_many(_work)

    def create(self, name, company_id, owner_id, created_by, **kwargs):
        """Create a new form. Returns the new form ID."""
        def _work(cursor):
            slug = self._generate_slug(cursor, name)
            cursor.execute('''
                INSERT INTO forms
                    (name, slug, description, company_id, owner_id, created_by,
                     schema, settings, utm_config, branding, requires_approval)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                name, slug, kwargs.get('description'),
                company_id, owner_id, created_by,
                json.dumps(kwargs.get('schema', [])),
                json.dumps(kwargs.get('settings', {})),
                json.dumps(kwargs.get('utm_config', {})),
                json.dumps(kwargs.get('branding', {})),
                kwargs.get('requires_approval', False),
            ))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update(self, form_id, **kwargs):
        """Update form fields. Returns True if rows affected."""
        allowed = {
            'name', 'description', 'schema', 'settings', 'utm_config',
            'branding', 'requires_approval', 'status', 'owner_id',
        }
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                if key in ('schema', 'settings', 'utm_config', 'branding'):
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                updates.append(f'{key} = %s')
                params.append(val)

        if not updates:
            return False

        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(form_id)
        set_clause = ', '.join(updates)
        return self.execute(
            f'UPDATE forms SET {set_clause} WHERE id = %s AND deleted_at IS NULL',
            params
        ) > 0

    def publish(self, form_id):
        """Publish: copy schema → published_schema, bump version, set status."""
        return self.execute('''
            UPDATE forms
            SET published_schema = schema,
                status = 'published',
                version = version + 1,
                published_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL
        ''', (form_id,)) > 0

    def disable(self, form_id):
        """Disable a published form."""
        return self.execute('''
            UPDATE forms
            SET status = 'disabled', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL
        ''', (form_id,)) > 0

    def duplicate(self, form_id, created_by):
        """Clone a form. Returns new form ID."""
        def _work(cursor):
            cursor.execute('''
                SELECT name, description, company_id, owner_id, schema,
                       settings, utm_config, branding, requires_approval
                FROM forms WHERE id = %s AND deleted_at IS NULL
            ''', (form_id,))
            src = cursor.fetchone()
            if not src:
                return None

            new_name = f"{src['name']} (Copy)"
            slug = self._generate_slug(cursor, new_name)

            cursor.execute('''
                INSERT INTO forms
                    (name, slug, description, company_id, owner_id, created_by,
                     schema, settings, utm_config, branding, requires_approval)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                new_name, slug, src['description'],
                src['company_id'], src['owner_id'], created_by,
                json.dumps(src['schema']),
                json.dumps(src['settings']),
                json.dumps(src['utm_config']),
                json.dumps(src['branding']),
                src['requires_approval'],
            ))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def soft_delete(self, form_id):
        """Soft-delete a form."""
        return self.execute(
            'UPDATE forms SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL',
            (form_id,)
        ) > 0

    def count_submissions(self, form_id):
        """Get total submission count for a form."""
        row = self.query_one(
            'SELECT COUNT(*) as total FROM form_submissions WHERE form_id = %s',
            (form_id,)
        )
        return row['total'] if row else 0

    # ---- Helpers ----

    def _generate_slug(self, cursor, name):
        """Generate a unique slug from the form name."""
        base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        if not base:
            base = 'form'
        slug = base
        counter = 1
        while True:
            cursor.execute(
                'SELECT 1 FROM forms WHERE slug = %s AND deleted_at IS NULL',
                (slug,)
            )
            if not cursor.fetchone():
                return slug
            slug = f'{base}-{counter}'
            counter += 1
