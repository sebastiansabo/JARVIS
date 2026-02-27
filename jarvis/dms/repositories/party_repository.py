"""Repository for document_parties table."""
from psycopg2.extras import Json
from core.base_repository import BaseRepository


class PartyRepository(BaseRepository):

    def get_by_document(self, document_id):
        """Get all parties for a document."""
        return self.query_all(
            'SELECT * FROM document_parties WHERE document_id = %s ORDER BY sort_order, id',
            (document_id,)
        )

    def get_by_id(self, party_id):
        return self.query_one(
            'SELECT * FROM document_parties WHERE id = %s',
            (party_id,)
        )

    def create(self, document_id, party_role, entity_name, **kwargs):
        return self.execute('''
            INSERT INTO document_parties
                (document_id, party_role, entity_type, entity_id, entity_name, entity_details, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        ''', (
            document_id,
            party_role,
            kwargs.get('entity_type', 'company'),
            kwargs.get('entity_id'),
            entity_name,
            Json(kwargs.get('entity_details', {})),
            kwargs.get('sort_order', 0),
        ), returning=True)

    def update(self, party_id, **fields):
        sets = []
        params = []
        for key in ('party_role', 'entity_type', 'entity_id', 'entity_name', 'sort_order'):
            if key in fields:
                sets.append(f'{key} = %s')
                params.append(fields[key])
        if 'entity_details' in fields:
            sets.append('entity_details = %s::jsonb')
            params.append(Json(fields['entity_details']))
        if not sets:
            return None
        params.append(party_id)
        return self.execute(
            f'UPDATE document_parties SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        )

    def delete(self, party_id):
        return self.execute(
            'DELETE FROM document_parties WHERE id = %s',
            (party_id,)
        )

    def delete_by_document(self, document_id):
        return self.execute(
            'DELETE FROM document_parties WHERE document_id = %s',
            (document_id,)
        )

    def suggest(self, query, company_id=None, limit=10):
        """Auto-suggest parties from companies, suppliers, and invoice suppliers."""
        escaped = query.replace('%', r'\%').replace('_', r'\_')
        like = f'%{escaped}%'
        results = []
        seen_names = set()

        # 1. Own companies
        cond = 'WHERE company ILIKE %s'
        params = [like]
        if company_id:
            cond += ' AND id = %s'
            params.append(company_id)
        params.append(limit)
        companies = self.query_all(f'''
            SELECT id, company AS name, 'company' AS entity_type, 'company' AS source,
                   vat AS cui, NULL AS phone, NULL AS email, vat
            FROM companies {cond}
            ORDER BY company LIMIT %s
        ''', tuple(params))
        for c in companies:
            results.append(c)
            seen_names.add(c['name'].lower())

        # 2. Suppliers table
        scond = 'WHERE is_active = TRUE AND name ILIKE %s'
        sparams = [like]
        if company_id:
            scond += ' AND company_id = %s'
            sparams.append(company_id)
        sparams.append(limit)
        suppliers = self.query_all(f'''
            SELECT id, name, supplier_type AS entity_type, 'supplier' AS source,
                   cui, phone, email, NULL AS vat
            FROM suppliers {scond}
            ORDER BY name LIMIT %s
        ''', tuple(sparams))
        for s in suppliers:
            results.append(s)
            seen_names.add(s['name'].lower())

        # 3. Accounting suppliers (DISTINCT from invoices) — skip if already in suppliers
        inv_params = [like]
        inv_cond = 'WHERE supplier ILIKE %s AND supplier IS NOT NULL'
        if company_id:
            inv_cond += ' AND company_id = %s'
            inv_params.append(company_id)
        inv_params.append(limit)
        invoices = self.query_all(f'''
            SELECT DISTINCT supplier AS name
            FROM invoices {inv_cond}
            ORDER BY supplier LIMIT %s
        ''', tuple(inv_params))
        for inv in invoices:
            if inv['name'] and inv['name'].lower() not in seen_names:
                results.append({
                    'id': None,
                    'name': inv['name'],
                    'entity_type': 'external',
                    'source': 'invoice',
                    'cui': None,
                    'phone': None,
                    'email': None,
                    'vat': None,
                })
                seen_names.add(inv['name'].lower())

        return results[:limit]
