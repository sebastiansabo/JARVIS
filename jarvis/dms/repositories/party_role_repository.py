"""Repository for dms_party_roles table."""
from core.base_repository import BaseRepository


class PartyRoleRepository(BaseRepository):

    def list_all(self, active_only=True):
        """List all party roles, ordered by sort_order."""
        where = 'WHERE is_active = TRUE' if active_only else ''
        return self.query_all(f'''
            SELECT * FROM dms_party_roles
            {where}
            ORDER BY sort_order, label
        ''')

    def get_by_id(self, role_id):
        return self.query_one(
            'SELECT * FROM dms_party_roles WHERE id = %s', (role_id,)
        )

    def get_by_slug(self, slug):
        return self.query_one(
            'SELECT * FROM dms_party_roles WHERE slug = %s AND is_active = TRUE', (slug,)
        )

    def create(self, slug, label, **kwargs):
        return self.execute('''
            INSERT INTO dms_party_roles (slug, label, sort_order, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (
            slug, label,
            kwargs.get('sort_order', 0),
            kwargs.get('is_active', True),
        ), returning=True)

    def update(self, role_id, **fields):
        # If slug is changing, cascade to document_parties.party_role
        new_slug = fields.get('slug')
        if new_slug:
            old = self.get_by_id(role_id)
            if old and old['slug'] != new_slug:
                def _cascade(cursor):
                    cursor.execute(
                        'UPDATE document_parties SET party_role = %s WHERE party_role = %s',
                        (new_slug, old['slug'])
                    )
                    sets = []
                    params = []
                    for key in ('slug', 'label', 'sort_order', 'is_active'):
                        if key in fields:
                            sets.append(f'{key} = %s')
                            params.append(fields[key])
                    sets.append('updated_at = CURRENT_TIMESTAMP')
                    params.append(role_id)
                    cursor.execute(
                        f'UPDATE dms_party_roles SET {", ".join(sets)} WHERE id = %s',
                        tuple(params)
                    )
                    return cursor.rowcount
                return self.execute_many(_cascade)

        sets = []
        params = []
        for key in ('slug', 'label', 'sort_order', 'is_active'):
            if key in fields:
                sets.append(f'{key} = %s')
                params.append(fields[key])
        if not sets:
            return None
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(role_id)
        return self.execute(
            f'UPDATE dms_party_roles SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def delete(self, role_id):
        return self.execute(
            'UPDATE dms_party_roles SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (role_id,)
        )

    def reorder(self, role_ids):
        """Bulk-update sort_order based on list position."""
        def _reorder(cursor):
            for idx, rid in enumerate(role_ids):
                cursor.execute(
                    'UPDATE dms_party_roles SET sort_order = %s WHERE id = %s',
                    (idx + 1, rid)
                )
            return len(role_ids)
        return self.execute_many(_reorder)
