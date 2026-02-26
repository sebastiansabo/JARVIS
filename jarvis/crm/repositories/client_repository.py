"""CRM Client Repository — CRUD + search + dedup for crm_clients."""

from core.base_repository import BaseRepository


class ClientRepository(BaseRepository):

    def get_by_id(self, client_id):
        return self.query_one('SELECT * FROM crm_clients WHERE id = %s', (client_id,))

    _ALLOWED_SORT = {
        'updated_at', 'created_at', 'display_name', 'id',
        'nr_reg', 'client_type', 'phone', 'email', 'city',
        'region', 'responsible', 'company_name', 'street', 'country',
        'client_since',
    }

    def search(self, name=None, phone=None, email=None, client_type=None,
               responsible=None, city=None, date_from=None, date_to=None,
               sort_by=None, sort_order=None, show_blacklisted=None,
               limit=50, offset=0):
        conditions, params = ['c.merged_into_id IS NULL'], []
        if show_blacklisted == 'only':
            conditions.append('c.is_blacklisted = TRUE')
        elif show_blacklisted != 'all':
            conditions.append('(c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)')
        if name:
            conditions.append('c.name_normalized ILIKE %s')
            params.append(f'%{name.lower()}%')
        if phone:
            conditions.append('c.phone = %s')
            params.append(phone)
        if email:
            conditions.append('c.email ILIKE %s')
            params.append(f'%{email}%')
        if client_type:
            conditions.append('c.client_type = %s')
            params.append(client_type)
        if responsible:
            conditions.append('c.responsible ILIKE %s')
            params.append(f'%{responsible}%')
        if city:
            conditions.append('c.city ILIKE %s')
            params.append(f'%{city}%')
        if date_from:
            conditions.append('c.created_at >= %s')
            params.append(date_from)
        if date_to:
            conditions.append("c.created_at < (%s::date + INTERVAL '1 day')")
            params.append(date_to)
        where = ' AND '.join(conditions)
        col = sort_by if sort_by in self._ALLOWED_SORT else 'updated_at'
        direction = 'ASC' if sort_order and sort_order.upper() == 'ASC' else 'DESC'
        order_col = 'client_since' if col == 'client_since' else f'c.{col}'
        params_count = tuple(params)
        params.extend([limit, offset])
        rows = self.query_all(
            f'''SELECT c.*,
                       (SELECT MIN(d.contract_date) FROM crm_deals d WHERE d.client_id = c.id) as client_since
                FROM crm_clients c
                WHERE {where}
                ORDER BY {order_col} {direction} NULLS LAST
                LIMIT %s OFFSET %s''',
            tuple(params)
        )
        count_row = self.query_one(
            f'SELECT COUNT(*) as count FROM crm_clients c WHERE {where}',
            params_count
        )
        return rows, count_row['count']

    def find_by_phone(self, phone):
        if not phone:
            return None
        return self.query_one(
            'SELECT * FROM crm_clients WHERE phone = %s AND merged_into_id IS NULL LIMIT 1',
            (phone,)
        )

    def find_by_name_trigram(self, name_normalized, threshold=0.7):
        if not name_normalized:
            return None
        return self.query_one(
            '''SELECT *, similarity(name_normalized, %s) as sim
               FROM crm_clients
               WHERE merged_into_id IS NULL
                 AND similarity(name_normalized, %s) >= %s
               ORDER BY sim DESC LIMIT 1''',
            (name_normalized, name_normalized, threshold)
        )

    def create(self, display_name, name_normalized, client_type='person',
               phone=None, phone_raw=None, email=None, street=None, city=None,
               region=None, company_name=None, responsible=None, source_flags=None):
        import json
        return self.execute(
            '''INSERT INTO crm_clients
               (display_name, name_normalized, client_type, phone, phone_raw,
                email, street, city, region, company_name, responsible, source_flags)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id''',
            (display_name, name_normalized, client_type, phone, phone_raw,
             email, street, city, region, company_name, responsible,
             json.dumps(source_flags or {})),
            returning=True
        )

    def update_source_flags(self, client_id, source_key):
        self.execute(
            """UPDATE crm_clients
               SET source_flags = source_flags || %s::jsonb, updated_at = NOW()
               WHERE id = %s""",
            (f'{{"{source_key}": true}}', client_id)
        )

    def get_cities(self):
        return self.query_all('''
            SELECT DISTINCT city FROM crm_clients
            WHERE merged_into_id IS NULL AND city IS NOT NULL AND city != ''
            ORDER BY city
        ''')

    def get_responsibles(self):
        return self.query_all('''
            SELECT DISTINCT responsible FROM crm_clients
            WHERE merged_into_id IS NULL AND responsible IS NOT NULL AND responsible != ''
            ORDER BY responsible
        ''')

    def get_stats(self):
        return self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE merged_into_id IS NULL AND (is_blacklisted = FALSE OR is_blacklisted IS NULL)) as total,
                COUNT(*) FILTER (WHERE client_type = 'person' AND merged_into_id IS NULL AND (is_blacklisted = FALSE OR is_blacklisted IS NULL)) as persons,
                COUNT(*) FILTER (WHERE client_type = 'company' AND merged_into_id IS NULL AND (is_blacklisted = FALSE OR is_blacklisted IS NULL)) as companies,
                COUNT(*) FILTER (WHERE merged_into_id IS NOT NULL) as merged,
                COUNT(*) FILTER (WHERE is_blacklisted = TRUE AND merged_into_id IS NULL) as blacklisted
            FROM crm_clients
        ''')

    def get_detailed_stats(self):
        """Client stats for the Statistics tab."""
        base = "FROM crm_clients WHERE merged_into_id IS NULL AND (is_blacklisted = FALSE OR is_blacklisted IS NULL)"

        total = self.query_one(f'SELECT COUNT(*) as count {base}')['count']

        by_type = self.query_all(f'''
            SELECT client_type, COUNT(*) as count {base}
            GROUP BY client_type ORDER BY count DESC
        ''')
        by_region = self.query_all(f'''
            SELECT COALESCE(region, 'Unknown') as region, COUNT(*) as count {base}
            GROUP BY region ORDER BY count DESC LIMIT 20
        ''')
        by_city = self.query_all(f'''
            SELECT COALESCE(city, 'Unknown') as city, COUNT(*) as count {base}
            GROUP BY city ORDER BY count DESC LIMIT 20
        ''')
        by_responsible = self.query_all(f'''
            SELECT COALESCE(responsible, 'Unassigned') as responsible, COUNT(*) as count {base}
            GROUP BY responsible ORDER BY count DESC LIMIT 20
        ''')
        with_deals = self.query_one('''
            SELECT COUNT(DISTINCT d.client_id) as clients_with_deals,
                   COUNT(*) as total_deals
            FROM crm_deals d
            JOIN crm_clients c ON c.id = d.client_id
            WHERE d.client_id IS NOT NULL AND (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)
        ''')

        # Contact info coverage
        contact = self.query_one(f'''
            SELECT
                COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '') as with_phone,
                COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '') as with_email,
                COUNT(*) FILTER (WHERE region IS NOT NULL AND region != '') as with_region,
                COUNT(*) FILTER (WHERE city IS NOT NULL AND city != '') as with_city,
                COUNT(*) FILTER (WHERE street IS NOT NULL AND street != '') as with_street
            {base}
        ''')

        # Data quality
        quality = self.query_one(f'''
            SELECT
                COUNT(*) FILTER (WHERE phone IS NULL OR phone = '') as missing_phone,
                COUNT(*) FILTER (WHERE email IS NULL OR email = '') as missing_email,
                COUNT(*) FILTER (WHERE region IS NULL OR region = '') as missing_region,
                COUNT(*) FILTER (WHERE responsible IS NULL OR responsible = '') as missing_responsible
            {base}
        ''')
        merged_count = self.query_one(
            'SELECT COUNT(*) as count FROM crm_clients WHERE merged_into_id IS NOT NULL'
        )['count']

        # Source flags breakdown
        source_flags = self.query_all(f'''
            SELECT key as source, COUNT(*) as count
            FROM crm_clients, jsonb_each_text(source_flags) AS kv(key, val)
            WHERE merged_into_id IS NULL AND val = 'true'
            GROUP BY key ORDER BY count DESC
        ''')

        # Monthly growth (last 12 months)
        by_month = self.query_all(f'''
            SELECT TO_CHAR(created_at, 'YYYY-MM') as month, COUNT(*) as count
            {base} AND created_at >= NOW() - INTERVAL '12 months'
            GROUP BY month ORDER BY month
        ''')

        return {
            'total': total,
            'by_type': by_type,
            'by_region': by_region,
            'by_city': by_city,
            'by_responsible': by_responsible,
            'clients_with_deals': with_deals['clients_with_deals'],
            'total_deals_linked': with_deals['total_deals'],
            'contact_coverage': {
                'with_phone': contact['with_phone'],
                'with_email': contact['with_email'],
                'with_region': contact['with_region'],
                'with_city': contact['with_city'],
                'with_street': contact['with_street'],
            },
            'data_quality': {
                'missing_phone': quality['missing_phone'],
                'missing_email': quality['missing_email'],
                'missing_region': quality['missing_region'],
                'missing_responsible': quality['missing_responsible'],
                'merged_clients': merged_count,
            },
            'source_flags': source_flags,
            'by_month': by_month,
        }

    _EDITABLE = {
        'display_name', 'client_type', 'phone', 'email', 'street',
        'city', 'region', 'company_name', 'responsible', 'nr_reg',
        'is_blacklisted',
    }

    def update(self, client_id, data):
        fields = {k: (None if v == '' else v) for k, v in data.items() if k in self._EDITABLE}
        if not fields:
            return None
        # Keep name_normalized in sync
        if 'display_name' in fields and fields['display_name']:
            fields['name_normalized'] = fields['display_name'].lower().strip()
        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [client_id]
        self.execute(
            f'UPDATE crm_clients SET {sets}, updated_at = NOW() WHERE id = %s',
            tuple(vals)
        )
        return self.get_by_id(client_id)

    def delete(self, client_id):
        return self.execute('DELETE FROM crm_clients WHERE id = %s', (client_id,)) > 0

    def toggle_blacklist(self, client_id, is_blacklisted):
        self.execute(
            'UPDATE crm_clients SET is_blacklisted = %s, updated_at = NOW() WHERE id = %s',
            (is_blacklisted, client_id)
        )
        return self.get_by_id(client_id)

    def batch_blacklist(self, client_ids, is_blacklisted):
        if not client_ids:
            return 0
        placeholders = ','.join(['%s'] * len(client_ids))
        return self.execute(
            f'UPDATE crm_clients SET is_blacklisted = %s, updated_at = NOW() WHERE id IN ({placeholders})',
            (is_blacklisted, *client_ids)
        )

    def batch_delete(self, client_ids):
        if not client_ids:
            return 0
        placeholders = ','.join(['%s'] * len(client_ids))
        return self.execute(
            f'DELETE FROM crm_clients WHERE id IN ({placeholders})',
            tuple(client_ids)
        )

    def merge(self, keep_id, remove_id):
        """Merge remove_id into keep_id. Updates all FKs."""
        def _work(cursor):
            cursor.execute('UPDATE crm_deals SET client_id = %s WHERE client_id = %s', (keep_id, remove_id))
            cursor.execute('UPDATE crm_clients SET merged_into_id = %s, updated_at = NOW() WHERE id = %s',
                           (keep_id, remove_id))
            # Merge source_flags
            cursor.execute('''
                UPDATE crm_clients SET source_flags = source_flags || (
                    SELECT source_flags FROM crm_clients WHERE id = %s
                ), updated_at = NOW()
                WHERE id = %s
            ''', (remove_id, keep_id))
            return True
        return self.execute_many(_work)
