"""Repository for suppliers table (master supplier list)."""
from core.base_repository import BaseRepository


class SupplierRepository(BaseRepository):

    def list_all(self, company_id=None, active_only=True, search=None,
                 supplier_type=None, limit=50, offset=0):
        conditions = []
        params = []

        if company_id:
            conditions.append('s.company_id = %s')
            params.append(company_id)
        if active_only:
            conditions.append('s.is_active = TRUE')
        if supplier_type:
            conditions.append('s.supplier_type = %s')
            params.append(supplier_type)
        if search:
            escaped = search.replace('%', r'\%').replace('_', r'\_')
            conditions.append('(s.name ILIKE %s OR s.cui ILIKE %s)')
            params.extend([f'%{escaped}%', f'%{escaped}%'])

        where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
        params.extend([limit, offset])

        return self.query_all(f'''
            SELECT s.*,
                   COALESCE(dc.doc_count, 0) AS document_count,
                   dc.linked_documents,
                   COALESCE(inv.invoice_count, 0) AS invoice_count,
                   COALESCE(inv.total_ron, 0) AS total_ron,
                   COALESCE(inv.total_eur, 0) AS total_eur
            FROM suppliers s
            LEFT JOIN (
                SELECT dp.entity_name,
                       COUNT(DISTINCT dp.document_id) AS doc_count,
                       json_agg(json_build_object(
                           'id', d.id, 'title', d.title
                       ) ORDER BY d.title) FILTER (WHERE d.id IS NOT NULL) AS linked_documents
                FROM document_parties dp
                JOIN dms_documents d ON d.id = dp.document_id
                WHERE dp.entity_name IS NOT NULL
                GROUP BY dp.entity_name
            ) dc ON dc.entity_name = s.name
            LEFT JOIN (
                SELECT supplier,
                       COUNT(*) AS invoice_count,
                       SUM(value_ron) AS total_ron,
                       SUM(value_eur) AS total_eur
                FROM invoices
                WHERE deleted_at IS NULL AND supplier IS NOT NULL
                GROUP BY supplier
            ) inv ON inv.supplier = s.name
            {where}
            ORDER BY s.name
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
            conditions.append('(name ILIKE %s OR cui ILIKE %s)')
            params.extend([f'%{escaped}%', f'%{escaped}%'])

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
                 contact_name, contact_function, contact_email, contact_phone,
                 owner_name, owner_function, owner_email, owner_phone,
                 company_id, created_by, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            kwargs.get('contact_name'),
            kwargs.get('contact_function'),
            kwargs.get('contact_email'),
            kwargs.get('contact_phone'),
            kwargs.get('owner_name'),
            kwargs.get('owner_function'),
            kwargs.get('owner_email'),
            kwargs.get('owner_phone'),
            company_id,
            created_by,
            kwargs.get('is_active', True),
        ), returning=True)

    def update(self, supplier_id, **fields):
        sets = []
        params = []
        allowed = ('name', 'supplier_type', 'cui', 'j_number', 'address', 'city',
                    'county', 'nr_reg_com', 'bank_account', 'iban', 'bank_name',
                    'phone', 'email', 'is_active',
                    'contact_name', 'contact_function', 'contact_email', 'contact_phone',
                    'owner_name', 'owner_function', 'owner_email', 'owner_phone')
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

    def get_by_cui(self, cui, company_id=None):
        """Find a supplier by CUI/CIF."""
        if not cui:
            return None
        conditions = ['cui = %s', 'is_active = TRUE']
        params = [cui.strip()]
        if company_id:
            conditions.append('company_id = %s')
            params.append(company_id)
        return self.query_one(
            f"SELECT * FROM suppliers WHERE {' AND '.join(conditions)}",
            tuple(params),
        )

    def search(self, query, company_id=None, limit=10):
        """Lightweight search for autocomplete (matches name or CUI)."""
        escaped = query.replace('%', r'\%').replace('_', r'\_')
        like = f'%{escaped}%'
        conditions = ['is_active = TRUE', '(name ILIKE %s OR cui ILIKE %s)']
        params = [like, like]
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
