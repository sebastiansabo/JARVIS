"""Repository for dms_relationship_types table."""
from core.base_repository import BaseRepository


class RelTypeRepository(BaseRepository):

    def list_all(self, active_only=True):
        """List all relationship types, ordered by sort_order."""
        where = 'WHERE is_active = TRUE' if active_only else ''
        return self.query_all(f'''
            SELECT * FROM dms_relationship_types
            {where}
            ORDER BY sort_order, label
        ''')

    def get_by_id(self, type_id):
        return self.query_one(
            'SELECT * FROM dms_relationship_types WHERE id = %s', (type_id,)
        )

    def get_by_slug(self, slug):
        return self.query_one(
            'SELECT * FROM dms_relationship_types WHERE slug = %s AND is_active = TRUE', (slug,)
        )

    def create(self, slug, label, **kwargs):
        return self.execute('''
            INSERT INTO dms_relationship_types (slug, label, icon, color, sort_order, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            slug, label,
            kwargs.get('icon', 'bi-file-earmark'),
            kwargs.get('color', '#6c757d'),
            kwargs.get('sort_order', 0),
            kwargs.get('is_active', True),
        ), returning=True)

    def update(self, type_id, **fields):
        # If slug is changing, cascade to dms_documents.relationship_type
        new_slug = fields.get('slug')
        if new_slug:
            old = self.get_by_id(type_id)
            if old and old['slug'] != new_slug:
                def _cascade(cursor):
                    cursor.execute(
                        'UPDATE dms_documents SET relationship_type = %s WHERE relationship_type = %s',
                        (new_slug, old['slug'])
                    )
                    sets = []
                    params = []
                    for key in ('slug', 'label', 'icon', 'color', 'sort_order', 'is_active'):
                        if key in fields:
                            sets.append(f'{key} = %s')
                            params.append(fields[key])
                    sets.append('updated_at = CURRENT_TIMESTAMP')
                    params.append(type_id)
                    cursor.execute(
                        f'UPDATE dms_relationship_types SET {", ".join(sets)} WHERE id = %s',
                        tuple(params)
                    )
                    return cursor.rowcount
                return self.execute_many(_cascade)

        sets = []
        params = []
        for key in ('slug', 'label', 'icon', 'color', 'sort_order', 'is_active'):
            if key in fields:
                sets.append(f'{key} = %s')
                params.append(fields[key])
        if not sets:
            return None
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(type_id)
        return self.execute(
            f'UPDATE dms_relationship_types SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def delete(self, type_id):
        return self.execute(
            'UPDATE dms_relationship_types SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (type_id,)
        )

    def reorder(self, type_ids):
        """Bulk-update sort_order based on list position."""
        def _reorder(cursor):
            for idx, tid in enumerate(type_ids):
                cursor.execute(
                    'UPDATE dms_relationship_types SET sort_order = %s WHERE id = %s',
                    (idx + 1, tid)
                )
            return len(type_ids)
        return self.execute_many(_reorder)
