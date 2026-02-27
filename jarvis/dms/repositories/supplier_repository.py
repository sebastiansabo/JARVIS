"""Repository for suppliers table (master supplier list)."""
from core.base_repository import BaseRepository


class SupplierRepository(BaseRepository):

    def list_all(self, company_id=None, active_only=True, search=None,
                 supplier_type=None, limit=50, offset=0):
        conditions = []
        params = []

        if company_id:
            conditions.append('company_id = %s')
            params.append(company_id)
        if active_only:
            conditions.append('is_active = TRUE')
        if supplier_type:
            conditions.append('supplier_type = %s')
            params.append(supplier_type)
        if search:
            escaped = search.replace('%', r'\%').replace('_', r'\_')
            conditions.append('name ILIKE %s')
            params.append(f'%{escaped}%')

        where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
        params.extend([limit, offset])

        return self.query_all(f'''
            SELECT * FROM suppliers {where}
            ORDER BY name
            LIMIT %s OFFSET %s
        ''', tuple(params))

    def count(self, company_id=None, active_only=True, search=None, supplier_type=None):
        conditions = []
        params = []

        if company_id:
            conditions.append('company_id = %s')
            params.append(company_id)
        if active_only:
            conditions.append('is_active = TRUE')
        if supplier_type:
            conditions.append('supplier_type = %s')
            params.append(supplier_type)
        if search:
            escaped = search.replace('%', r'\%').replace('_', r'\_')
            conditions.append('name ILIKE %s')
            params.append(f'%{escaped}%')

        where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
        row = self.query_one(f'SELECT COUNT(*) AS cnt FROM suppliers {where}', tuple(params))
        return row['cnt'] if row else 0

    def get_by_id(self, supplier_id):
        return self.query_one('SELECT * FROM suppliers WHERE id = %s', (supplier_id,))

    def create(self, name, company_id, created_by, **kwargs):
        return self.execute('''
            INSERT INTO suppliers
                (name, supplier_type, cui, j_number, address, city, county, nr_reg_com,
                 bank_account, iban, bank_name, phone, email,
                 company_id, created_by, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            name,
            kwargs.get('supplier_type', 'company'),
            kwargs.get('cui'),
            kwargs.get('j_number'),
            kwargs.get('address'),
            kwargs.get('city'),
            kwargs.get('county'),
            kwargs.get('nr_reg_com'),
            kwargs.get('bank_account'),
            kwargs.get('iban'),
            kwargs.get('bank_name'),
            kwargs.get('phone'),
            kwargs.get('email'),
            company_id,
            created_by,
            kwargs.get('is_active', True),
        ), returning=True)

    def update(self, supplier_id, **fields):
        sets = []
        params = []
        allowed = ('name', 'supplier_type', 'cui', 'j_number', 'address', 'city',
                    'county', 'nr_reg_com', 'bank_account', 'iban', 'bank_name',
                    'phone', 'email', 'is_active')
        for key in allowed:
            if key in fields:
                sets.append(f'{key} = %s')
                params.append(fields[key])
        if not sets:
            return None
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(supplier_id)
        return self.execute(
            f'UPDATE suppliers SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def delete(self, supplier_id):
        """Soft-delete."""
        return self.execute(
            'UPDATE suppliers SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (supplier_id,)
        )

    def search(self, query, company_id=None, limit=10):
        """Lightweight search for autocomplete."""
        escaped = query.replace('%', r'\%').replace('_', r'\_')
        like = f'%{escaped}%'
        conditions = ['is_active = TRUE', 'name ILIKE %s']
        params = [like]
        if company_id:
            conditions.append('company_id = %s')
            params.append(company_id)
        params.append(limit)
        return self.query_all(f'''
            SELECT id, name, supplier_type, cui, phone, email
            FROM suppliers
            WHERE {' AND '.join(conditions)}
            ORDER BY name
            LIMIT %s
        ''', tuple(params))
