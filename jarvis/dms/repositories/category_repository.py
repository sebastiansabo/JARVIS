"""Repository for dms_categories table."""
from core.base_repository import BaseRepository


class CategoryRepository(BaseRepository):

    def list_all(self, company_id=None, active_only=True):
        """List categories for a company, falling back to global defaults."""
        conditions = []
        params = []

        if company_id:
            conditions.append('(c.company_id = %s OR c.company_id IS NULL)')
            params.append(company_id)

        if active_only:
            conditions.append('c.is_active = TRUE')

        where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''

        return self.query_all(f'''
            SELECT c.*,
                   COALESCE(doc_counts.cnt, 0) AS document_count
            FROM dms_categories c
            LEFT JOIN (
                SELECT category_id, COUNT(*) AS cnt
                FROM dms_documents
                WHERE deleted_at IS NULL AND parent_id IS NULL
                GROUP BY category_id
            ) doc_counts ON doc_counts.category_id = c.id
            {where}
            ORDER BY c.sort_order, c.name
        ''', tuple(params))

    def get_by_id(self, category_id):
        return self.query_one(
            'SELECT * FROM dms_categories WHERE id = %s', (category_id,)
        )

    def create(self, name, slug, company_id=None, **kwargs):
        return self.execute('''
            INSERT INTO dms_categories (name, slug, icon, color, description, company_id, sort_order, is_active, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            name, slug,
            kwargs.get('icon', 'bi-folder'),
            kwargs.get('color', '#6c757d'),
            kwargs.get('description'),
            company_id,
            kwargs.get('sort_order', 0),
            kwargs.get('is_active', True),
            kwargs.get('created_by'),
        ), returning=True)

    def update(self, category_id, **fields):
        sets = []
        params = []
        for key in ('name', 'slug', 'icon', 'color', 'description', 'sort_order', 'is_active'):
            if key in fields:
                sets.append(f'{key} = %s')
                params.append(fields[key])
        if not sets:
            return None
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(category_id)
        return self.execute(
            f'UPDATE dms_categories SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def delete(self, category_id):
        return self.execute(
            'UPDATE dms_categories SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (category_id,)
        )

    def reorder(self, category_ids):
        """Bulk-update sort_order based on list position."""
        def _reorder(cursor):
            for idx, cid in enumerate(category_ids):
                cursor.execute(
                    'UPDATE dms_categories SET sort_order = %s WHERE id = %s',
                    (idx + 1, cid)
                )
            return len(category_ids)
        return self.execute_many(_reorder)
