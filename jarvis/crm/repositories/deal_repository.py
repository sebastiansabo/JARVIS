"""CRM Deal Repository — CRUD + search for crm_deals (NW/GW car dossiers)."""

from core.base_repository import BaseRepository


class DealRepository(BaseRepository):

    def get_by_id(self, deal_id):
        return self.query_one(
            '''SELECT d.*, c.display_name as client_display_name
               FROM crm_deals d
               LEFT JOIN crm_clients c ON c.id = d.client_id
               WHERE d.id = %s''',
            (deal_id,)
        )

    _ALLOWED_SORT = {
        'source', 'dossier_number', 'brand', 'model_name', 'buyer_name',
        'dossier_status', 'sale_price_net', 'contract_date', 'dealer_name',
        'branch', 'order_number', 'vin', 'engine_code', 'fuel_type', 'color',
        'model_year', 'order_status', 'contract_status', 'sales_person',
        'owner_name', 'list_price', 'purchase_price_net', 'gross_profit',
        'discount_value', 'vehicle_type', 'registration_number', 'delivery_date',
        'updated_at', 'created_at', 'id',
    }

    def search(self, source=None, brand=None, model=None, buyer=None, vin=None,
               status=None, dealer=None, sales_person=None,
               date_from=None, date_to=None, client_id=None,
               sort_by=None, sort_order=None,
               limit=50, offset=0):
        conditions, params = ['(c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL OR d.client_id IS NULL)'], []
        if source:
            conditions.append('d.source = %s')
            params.append(source)
        if brand:
            conditions.append('d.brand ILIKE %s')
            params.append(f'%{brand}%')
        if model:
            conditions.append('d.model_name ILIKE %s')
            params.append(f'%{model}%')
        if buyer:
            conditions.append('d.buyer_name ILIKE %s')
            params.append(f'%{buyer}%')
        if vin:
            conditions.append('d.vin ILIKE %s')
            params.append(f'%{vin}%')
        if status:
            conditions.append('d.dossier_status ILIKE %s')
            params.append(f'%{status}%')
        if date_from:
            conditions.append('d.contract_date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('d.contract_date <= %s')
            params.append(date_to)
        if dealer:
            conditions.append('d.dealer_name ILIKE %s')
            params.append(f'%{dealer}%')
        if sales_person:
            conditions.append('d.sales_person ILIKE %s')
            params.append(f'%{sales_person}%')
        if client_id:
            conditions.append('d.client_id = %s')
            params.append(client_id)
        where = ' AND '.join(conditions)
        params_count = tuple(params)
        params.extend([limit, offset])
        order = 'd.contract_date DESC NULLS LAST, d.id DESC'
        if sort_by and sort_by in self._ALLOWED_SORT:
            direction = 'ASC' if sort_order == 'ASC' else 'DESC'
            nulls = 'NULLS LAST' if direction == 'ASC' else 'NULLS LAST'
            order = f'd.{sort_by} {direction} {nulls}, d.id DESC'
        rows = self.query_all(
            f'''SELECT d.*, c.display_name as client_display_name
                FROM crm_deals d
                LEFT JOIN crm_clients c ON c.id = d.client_id
                WHERE {where}
                ORDER BY {order}
                LIMIT %s OFFSET %s''',
            tuple(params)
        )
        count_row = self.query_one(
            f'''SELECT COUNT(*) as count FROM crm_deals d
                LEFT JOIN crm_clients c ON c.id = d.client_id
                WHERE {where}''',
            params_count
        )
        return rows, count_row['count']

    def upsert(self, source, dossier_number, row_hash, data, batch_id):
        """Insert or update deal by source+dossier_number. Returns (id, is_new)."""
        existing = self.query_one(
            'SELECT id, source_row_hash FROM crm_deals WHERE source = %s AND dossier_number = %s',
            (source, dossier_number)
        )
        if existing:
            if existing['source_row_hash'] == row_hash:
                return existing['id'], False  # unchanged
            cols = ', '.join(f'{k} = %s' for k in data.keys())
            vals = list(data.values()) + [row_hash, batch_id, existing['id']]
            self.execute(
                f'UPDATE crm_deals SET {cols}, source_row_hash = %s, import_batch_id = %s, updated_at = NOW() WHERE id = %s',
                tuple(vals)
            )
            return existing['id'], False
        else:
            data['source'] = source
            data['dossier_number'] = dossier_number
            data['source_row_hash'] = row_hash
            data['import_batch_id'] = batch_id
            cols = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            result = self.execute(
                f'INSERT INTO crm_deals ({cols}) VALUES ({placeholders}) RETURNING id',
                tuple(data.values()), returning=True
            )
            return result['id'], True

    def get_stats(self):
        return self.query_one('''
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE d.source = 'nw') as new_cars,
                COUNT(*) FILTER (WHERE d.source = 'gw') as used_cars,
                COUNT(DISTINCT d.brand) as brands
            FROM crm_deals d
            LEFT JOIN crm_clients c ON c.id = d.client_id
            WHERE (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL OR d.client_id IS NULL)
        ''')

    def get_detailed_stats(self, dealers=None, brands=None, statuses=None, date_from=None, date_to=None):
        """Rich stats for the Statistics tab, with optional filters.
        dealers/brands/statuses can be lists for multi-select.
        Excludes deals linked to blacklisted clients.
        """
        conditions, params = [
            '(client_id IS NULL OR client_id NOT IN (SELECT id FROM crm_clients WHERE is_blacklisted = TRUE))'
        ], []
        if dealers:
            placeholders = ','.join(['%s'] * len(dealers))
            conditions.append(f'dealer_name IN ({placeholders})')
            params.extend(dealers)
        if brands:
            placeholders = ','.join(['%s'] * len(brands))
            conditions.append(f'brand IN ({placeholders})')
            params.extend(brands)
        if statuses:
            placeholders = ','.join(['%s'] * len(statuses))
            conditions.append(f'dossier_status IN ({placeholders})')
            params.extend(statuses)
        if date_from:
            conditions.append('contract_date >= %s')
            params.append(date_from)
        if date_to:
            conditions.append('contract_date <= %s')
            params.append(date_to)
        where = ' AND '.join(conditions)
        p = tuple(params)

        by_brand = self.query_all(
            f'''SELECT brand, COUNT(*) as count,
                   COALESCE(SUM(sale_price_net), 0) as revenue
            FROM crm_deals WHERE brand IS NOT NULL AND {where}
            GROUP BY brand ORDER BY count DESC''', p)
        by_dealer = self.query_all(
            f'''SELECT dealer_name, COUNT(*) as count,
                   COALESCE(SUM(sale_price_net), 0) as revenue
            FROM crm_deals WHERE dealer_name IS NOT NULL AND {where}
            GROUP BY dealer_name ORDER BY count DESC''', p)
        by_sales_person = self.query_all(
            f'''SELECT sales_person, COUNT(*) as count,
                   COALESCE(SUM(sale_price_net), 0) as revenue
            FROM crm_deals WHERE sales_person IS NOT NULL AND {where}
            GROUP BY sales_person ORDER BY count DESC''', p)
        by_month = self.query_all(
            f'''SELECT TO_CHAR(contract_date, 'YYYY-MM') as month,
                   COUNT(*) as count,
                   COALESCE(SUM(sale_price_net), 0) as revenue
            FROM crm_deals WHERE contract_date IS NOT NULL AND {where}
            GROUP BY month ORDER BY month DESC LIMIT 24''', p)
        by_status = self.query_all(
            f'''SELECT dossier_status, COUNT(*) as count
            FROM crm_deals WHERE dossier_status IS NOT NULL AND {where}
            GROUP BY dossier_status ORDER BY count DESC''', p)
        totals = self.query_one(
            f'''SELECT COUNT(*) as total_deals,
                   COALESCE(SUM(sale_price_net), 0) as total_revenue,
                   COALESCE(AVG(sale_price_net), 0) as avg_price,
                   COUNT(DISTINCT brand) as brand_count,
                   COUNT(DISTINCT dealer_name) as dealer_count,
                   COUNT(DISTINCT sales_person) as sales_person_count
            FROM crm_deals WHERE {where}''', p)
        return {
            'totals': totals,
            'by_brand': by_brand,
            'by_dealer': by_dealer,
            'by_sales_person': by_sales_person,
            'by_month': by_month,
            'by_status': by_status,
        }

    _BL_FILTER = """(d.client_id IS NULL OR d.client_id NOT IN (
        SELECT id FROM crm_clients WHERE is_blacklisted = TRUE))"""

    def get_brands(self):
        return self.query_all(
            f"SELECT DISTINCT brand FROM crm_deals d WHERE brand IS NOT NULL AND {self._BL_FILTER} ORDER BY brand"
        )

    def get_dealers(self):
        return [r['dealer_name'] for r in self.query_all(
            f"SELECT DISTINCT dealer_name FROM crm_deals d WHERE dealer_name IS NOT NULL AND {self._BL_FILTER} ORDER BY dealer_name"
        )]

    def get_sales_persons(self):
        return [r['sales_person'] for r in self.query_all(
            f"SELECT DISTINCT sales_person FROM crm_deals d WHERE sales_person IS NOT NULL AND {self._BL_FILTER} ORDER BY sales_person"
        )]

    def get_statuses(self):
        return self.query_all(
            f"SELECT dossier_status, COUNT(*) as count FROM crm_deals d WHERE dossier_status IS NOT NULL AND {self._BL_FILTER} GROUP BY dossier_status ORDER BY count DESC"
        )

    def get_order_statuses(self):
        return [r['order_status'] for r in self.query_all(
            f"SELECT DISTINCT order_status FROM crm_deals d WHERE order_status IS NOT NULL AND {self._BL_FILTER} ORDER BY order_status"
        )]

    def get_contract_statuses(self):
        return [r['contract_status'] for r in self.query_all(
            f"SELECT DISTINCT contract_status FROM crm_deals d WHERE contract_status IS NOT NULL AND {self._BL_FILTER} ORDER BY contract_status"
        )]

    _EDITABLE = {
        'brand', 'model_name', 'buyer_name', 'dossier_status', 'order_status',
        'contract_status', 'sales_person', 'sale_price_net', 'color', 'fuel_type',
        'vehicle_type', 'registration_number', 'vin', 'engine_code', 'model_year',
        'dealer_name', 'branch', 'client_id',
    }

    def update(self, deal_id, data):
        fields = {k: (None if v == '' else v) for k, v in data.items() if k in self._EDITABLE}
        if not fields:
            return None
        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [deal_id]
        self.execute(
            f'UPDATE crm_deals SET {sets}, updated_at = NOW() WHERE id = %s',
            tuple(vals)
        )
        return self.get_by_id(deal_id)

    def delete(self, deal_id):
        return self.execute('DELETE FROM crm_deals WHERE id = %s', (deal_id,)) > 0
