"""Invoice repository - CRUD, search, bulk operations, drive links."""
import json
import time
import logging

from database import dict_from_row
from core.base_repository import BaseRepository
from core.cache import _cache_lock, _is_cache_valid

logger = logging.getLogger('jarvis.invoices')

# In-memory cache for invoice list (shorter TTL since data changes more frequently)
_invoices_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 60,  # 1 minute TTL
    'key': None  # Cache key based on query params
}


def clear_invoices_cache():
    """Clear the invoices and summary caches."""
    global _invoices_cache
    with _cache_lock:
        _invoices_cache = {'data': None, 'timestamp': 0, 'ttl': 60, 'key': None}
    # Also clear summary cache since it depends on invoice data
    from accounting.invoices.repositories.summary_repository import clear_summary_cache
    clear_summary_cache()
    logger.debug('Invoices and summary caches cleared')


class InvoiceRepository(BaseRepository):

    def save(self, supplier, invoice_template, invoice_number, invoice_date,
             invoice_value, currency, drive_link, distributions,
             value_ron=None, value_eur=None, exchange_rate=None,
             comment=None, payment_status='not_paid',
             subtract_vat=False, vat_rate=None, net_value=None,
             line_items=None, invoice_type='standard'):
        """Save invoice and its allocations to database. Returns the invoice ID."""
        def _work(cursor):
            cursor.execute('''
                INSERT INTO invoices (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate, comment, payment_status, subtract_vat, vat_rate, net_value, line_items, invoice_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate, comment, payment_status, subtract_vat, vat_rate, net_value, json.dumps(line_items) if line_items else None, invoice_type or 'standard'))
            invoice_id = cursor.fetchone()['id']

            # Use net_value for allocation calculations if VAT subtraction is enabled
            base_value = net_value if subtract_vat and net_value else invoice_value
            for dist in distributions:
                gross_allocation_value = base_value * dist['allocation']

                reinvoice_dests = dist.get('reinvoice_destinations', [])
                total_reinvoice_percent = sum(rd.get('percentage', 0) for rd in reinvoice_dests)
                net_percent = max(0, 100 - total_reinvoice_percent)
                allocation_value = gross_allocation_value * net_percent / 100

                responsible = dist.get('responsible', '')
                responsible_user_id = dist.get('responsible_user_id')
                if not responsible and dist['company'] and dist['department']:
                    conditions = ['ds.company = %s', 'ds.department = %s']
                    params = [dist['company'], dist['department']]

                    brand = dist.get('brand')
                    if brand:
                        conditions.append('ds.brand = %s')
                        params.append(brand)

                    subdept = dist.get('subdepartment')
                    if subdept:
                        conditions.append('ds.subdepartment = %s')
                        params.append(subdept)

                    assert all(isinstance(c, str) and '%s' in c for c in conditions), \
                        "SQL conditions must be parameterized strings"
                    cursor.execute(f'''
                        SELECT COALESCE(
                            (SELECT string_agg(u.name, ', ')
                             FROM unnest(ds.manager_ids) AS mid
                             JOIN users u ON u.id = mid),
                            ds.manager,
                            ''
                        ) AS manager_name,
                        (SELECT mid FROM unnest(ds.manager_ids) AS mid LIMIT 1) AS manager_user_id
                        FROM department_structure ds
                        WHERE {' AND '.join(conditions)}
                        LIMIT 1
                    ''', tuple(params))
                    row = cursor.fetchone()
                    if row and row['manager_name']:
                        responsible = row['manager_name']
                        responsible_user_id = row.get('manager_user_id')

                cursor.execute('''
                    INSERT INTO allocations (invoice_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsible, responsible_user_id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked, comment)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    invoice_id,
                    dist['company'],
                    dist.get('brand'),
                    dist['department'],
                    dist.get('subdepartment'),
                    dist['allocation'] * 100,
                    allocation_value,
                    responsible,
                    responsible_user_id,
                    dist.get('reinvoice_to'),
                    dist.get('reinvoice_brand'),
                    dist.get('reinvoice_department'),
                    dist.get('reinvoice_subdepartment'),
                    dist.get('locked', False),
                    dist.get('comment')
                ))
                allocation_id = cursor.fetchone()['id']

                for rd in reinvoice_dests:
                    rd_value = gross_allocation_value * (rd['percentage'] / 100)
                    cursor.execute('''
                        INSERT INTO reinvoice_destinations
                        (allocation_id, company, brand, department, subdepartment, percentage, value)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        allocation_id,
                        rd['company'],
                        rd.get('brand'),
                        rd.get('department'),
                        rd.get('subdepartment'),
                        rd['percentage'],
                        rd_value
                    ))

            clear_invoices_cache()
            return invoice_id

        try:
            return self.execute_many(_work)
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError(f"Invoice {invoice_number} already exists in database")
            raise

    def get_all(self, limit=100, offset=0, company=None, start_date=None,
                end_date=None, department=None, subdepartment=None,
                brand=None, status=None, payment_status=None,
                include_deleted=False):
        """Get all invoices with pagination and optional filtering."""
        query = 'SELECT DISTINCT i.* FROM invoices i'
        params = []
        conditions = []

        if company or department or subdepartment or brand:
            query = 'SELECT DISTINCT i.* FROM invoices i JOIN allocations a ON a.invoice_id = i.id'
            if company:
                conditions.append('a.company = %s')
                params.append(company)
            if department:
                conditions.append('a.department = %s')
                params.append(department)
            if subdepartment:
                conditions.append('a.subdepartment = %s')
                params.append(subdepartment)
            if brand:
                conditions.append('a.brand = %s')
                params.append(brand)

        if include_deleted:
            conditions.append('i.deleted_at IS NOT NULL')
        else:
            conditions.append('i.deleted_at IS NULL')

        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if status:
            conditions.append('i.status = %s')
            params.append(status)
        if payment_status:
            conditions.append('i.payment_status = %s')
            params.append(payment_status)

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' ORDER BY i.created_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        return self.query_all(query, params)

    def get_with_allocations(self, invoice_id):
        """Get invoice with all its allocations and their reinvoice destinations."""
        def _work(cursor):
            cursor.execute('SELECT * FROM invoices WHERE id = %s', (invoice_id,))
            invoice = cursor.fetchone()
            if not invoice:
                return None

            invoice = dict_from_row(invoice)

            cursor.execute('SELECT * FROM allocations WHERE invoice_id = %s', (invoice_id,))
            allocations = [dict_from_row(row) for row in cursor.fetchall()]

            allocation_ids = [alloc['id'] for alloc in allocations]
            reinvoice_map = {}

            if allocation_ids:
                placeholders = ','.join(['%s'] * len(allocation_ids))
                cursor.execute(f'''
                    SELECT id, allocation_id, company, brand, department, subdepartment, percentage, value
                    FROM reinvoice_destinations
                    WHERE allocation_id IN ({placeholders})
                ''', allocation_ids)

                for row in cursor.fetchall():
                    rd = dict_from_row(row)
                    alloc_id = rd.pop('allocation_id')
                    if alloc_id not in reinvoice_map:
                        reinvoice_map[alloc_id] = []
                    reinvoice_map[alloc_id].append(rd)

            for alloc in allocations:
                alloc['reinvoice_destinations'] = reinvoice_map.get(alloc['id'], [])

            invoice['allocations'] = allocations
            return invoice
        return self.execute_many(_work)

    def get_all_with_allocations(self, limit=100, offset=0, company=None,
                                  start_date=None, end_date=None,
                                  department=None, subdepartment=None,
                                  brand=None, status=None,
                                  payment_status=None, include_deleted=False):
        """Get all invoices with their allocations in a single optimized query."""
        global _invoices_cache

        cache_key = f"{limit}:{offset}:{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}:{status}:{payment_status}:{include_deleted}"

        if _is_cache_valid(_invoices_cache) and _invoices_cache.get('key') == cache_key:
            return _invoices_cache['data']

        params = []
        conditions = []

        if include_deleted:
            conditions.append('i.deleted_at IS NOT NULL')
        else:
            conditions.append('i.deleted_at IS NULL')

        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if status:
            conditions.append('i.status = %s')
            params.append(status)
        if payment_status:
            conditions.append('i.payment_status = %s')
            params.append(payment_status)

        allocation_filters = []
        if company:
            allocation_filters.append('a.company = %s')
            params.append(company)
        if department:
            allocation_filters.append('a.department = %s')
            params.append(department)
        if subdepartment:
            allocation_filters.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            allocation_filters.append('a.brand = %s')
            params.append(brand)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        if allocation_filters:
            allocation_filter_clause = ' AND '.join(allocation_filters)
            query = f'''
            WITH filtered_invoices AS (
                SELECT DISTINCT i.id
                FROM invoices i
                JOIN allocations a ON a.invoice_id = i.id
                WHERE {where_clause} AND {allocation_filter_clause}
                ORDER BY i.id DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                i.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'invoice_id', a.invoice_id,
                            'company', a.company,
                            'brand', a.brand,
                            'department', a.department,
                            'subdepartment', a.subdepartment,
                            'allocation_percent', a.allocation_percent,
                            'allocation_value', a.allocation_value,
                            'responsible', a.responsible,
                            'reinvoice_to', a.reinvoice_to,
                            'reinvoice_brand', a.reinvoice_brand,
                            'reinvoice_department', a.reinvoice_department,
                            'reinvoice_subdepartment', a.reinvoice_subdepartment,
                            'locked', a.locked,
                            'comment', a.comment,
                            'reinvoice_destinations', COALESCE(
                                (SELECT json_agg(
                                    json_build_object(
                                        'id', rd.id,
                                        'company', rd.company,
                                        'brand', rd.brand,
                                        'department', rd.department,
                                        'subdepartment', rd.subdepartment,
                                        'percentage', rd.percentage,
                                        'value', rd.value
                                    )
                                ) FROM reinvoice_destinations rd WHERE rd.allocation_id = a.id),
                                '[]'::json
                            )
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'::json
                ) as allocations
            FROM filtered_invoices fi
            JOIN invoices i ON i.id = fi.id
            LEFT JOIN allocations a ON a.invoice_id = i.id
            GROUP BY i.id
            ORDER BY i.created_at DESC
            '''
        else:
            query = f'''
            WITH paginated_invoices AS (
                SELECT i.*
                FROM invoices i
                WHERE {where_clause}
                ORDER BY i.created_at DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                pi.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'invoice_id', a.invoice_id,
                            'company', a.company,
                            'brand', a.brand,
                            'department', a.department,
                            'subdepartment', a.subdepartment,
                            'allocation_percent', a.allocation_percent,
                            'allocation_value', a.allocation_value,
                            'responsible', a.responsible,
                            'reinvoice_to', a.reinvoice_to,
                            'reinvoice_brand', a.reinvoice_brand,
                            'reinvoice_department', a.reinvoice_department,
                            'reinvoice_subdepartment', a.reinvoice_subdepartment,
                            'locked', a.locked,
                            'comment', a.comment,
                            'reinvoice_destinations', COALESCE(
                                (SELECT json_agg(
                                    json_build_object(
                                        'id', rd.id,
                                        'company', rd.company,
                                        'brand', rd.brand,
                                        'department', rd.department,
                                        'subdepartment', rd.subdepartment,
                                        'percentage', rd.percentage,
                                        'value', rd.value
                                    )
                                ) FROM reinvoice_destinations rd WHERE rd.allocation_id = a.id),
                                '[]'::json
                            )
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'::json
                ) as allocations
            FROM paginated_invoices pi
            LEFT JOIN allocations a ON a.invoice_id = pi.id
            GROUP BY pi.id, pi.supplier, pi.invoice_template, pi.invoice_number, pi.invoice_date,
                     pi.invoice_value, pi.currency, pi.value_ron, pi.value_eur, pi.exchange_rate,
                     pi.drive_link, pi.comment, pi.status, pi.payment_status, pi.deleted_at,
                     pi.created_at, pi.updated_at, pi.subtract_vat, pi.vat_rate, pi.net_value,
                     pi.line_items, pi.invoice_type
            ORDER BY pi.created_at DESC
            '''

        params.extend([limit, offset])

        def _work(cursor):
            cursor.execute(query, params)

            invoices = []
            for row in cursor.fetchall():
                invoice = dict_from_row(row)
                if isinstance(invoice.get('allocations'), str):
                    invoice['allocations'] = json.loads(invoice['allocations'])
                invoices.append(invoice)

            _invoices_cache['data'] = invoices
            _invoices_cache['timestamp'] = time.time()
            _invoices_cache['key'] = cache_key

            return invoices
        return self.execute_many(_work)

    def delete(self, invoice_id):
        """Soft delete an invoice (move to bin)."""
        deleted = self.execute(
            'UPDATE invoices SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL',
            (invoice_id,)) > 0
        if deleted:
            clear_invoices_cache()
        return deleted

    def restore(self, invoice_id):
        """Restore a soft-deleted invoice from the bin."""
        restored = self.execute(
            'UPDATE invoices SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL',
            (invoice_id,)) > 0
        if restored:
            clear_invoices_cache()
        return restored

    def get_drive_link(self, invoice_id):
        """Get the drive_link for a single invoice."""
        result = self.query_one('SELECT drive_link FROM invoices WHERE id = %s', (invoice_id,))
        return result['drive_link'] if result else None

    def get_drive_links(self, invoice_ids):
        """Get drive_links for multiple invoices. Returns list of non-null links."""
        if not invoice_ids:
            return []
        placeholders = ','.join(['%s'] * len(invoice_ids))
        results = self.query_all(
            f'SELECT drive_link FROM invoices WHERE id IN ({placeholders}) AND drive_link IS NOT NULL',
            invoice_ids)
        return [r['drive_link'] for r in results if r['drive_link']]

    def permanently_delete(self, invoice_id):
        """Permanently delete an invoice and its allocations."""
        deleted = self.execute('DELETE FROM invoices WHERE id = %s', (invoice_id,)) > 0
        if deleted:
            clear_invoices_cache()
        return deleted

    def bulk_soft_delete(self, invoice_ids):
        """Soft delete multiple invoices. Returns count of deleted invoices."""
        if not invoice_ids:
            return 0
        placeholders = ','.join(['%s'] * len(invoice_ids))
        deleted_count = self.execute(
            f'UPDATE invoices SET deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders}) AND deleted_at IS NULL',
            invoice_ids)
        if deleted_count > 0:
            clear_invoices_cache()
        return deleted_count

    def bulk_restore(self, invoice_ids):
        """Restore multiple soft-deleted invoices. Returns count of restored invoices."""
        if not invoice_ids:
            return 0
        placeholders = ','.join(['%s'] * len(invoice_ids))
        restored_count = self.execute(
            f'UPDATE invoices SET deleted_at = NULL WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL',
            invoice_ids)
        if restored_count > 0:
            clear_invoices_cache()
        return restored_count

    def bulk_permanently_delete(self, invoice_ids):
        """Permanently delete multiple invoices. Returns count of deleted invoices."""
        if not invoice_ids:
            return 0
        placeholders = ','.join(['%s'] * len(invoice_ids))
        deleted_count = self.execute(
            f'DELETE FROM invoices WHERE id IN ({placeholders})', invoice_ids)
        if deleted_count > 0:
            clear_invoices_cache()
        return deleted_count

    def cleanup_old_deleted(self, days=30):
        """Permanently delete invoices that have been in the bin for more than specified days."""
        deleted_count = self.execute('''
            DELETE FROM invoices
            WHERE deleted_at IS NOT NULL
            AND deleted_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
        ''', (days,))
        return deleted_count

    def update(self, invoice_id, supplier=None, invoice_number=None,
               invoice_date=None, invoice_value=None, currency=None,
               drive_link=None, comment=None, status=None,
               payment_status=None, subtract_vat=None, vat_rate=None,
               net_value=None):
        """Update an existing invoice."""
        updates = []
        params = []

        if supplier is not None:
            updates.append('supplier = %s')
            params.append(supplier)
        if invoice_number is not None:
            updates.append('invoice_number = %s')
            params.append(invoice_number)
        if invoice_date is not None:
            updates.append('invoice_date = %s')
            params.append(invoice_date)
        if invoice_value is not None:
            updates.append('invoice_value = %s')
            params.append(invoice_value)
        if currency is not None:
            updates.append('currency = %s')
            params.append(currency)
        if drive_link is not None:
            updates.append('drive_link = %s')
            params.append(drive_link)
        if comment is not None:
            updates.append('comment = %s')
            params.append(comment)
        if status is not None:
            updates.append('status = %s')
            params.append(status)
        if payment_status is not None:
            updates.append('payment_status = %s')
            params.append(payment_status)
        if subtract_vat is not None:
            updates.append('subtract_vat = %s')
            params.append(subtract_vat)
        if vat_rate is not None:
            updates.append('vat_rate = %s')
            params.append(vat_rate)
        elif subtract_vat is False:
            updates.append('vat_rate = %s')
            params.append(None)
        if net_value is not None:
            updates.append('net_value = %s')
            params.append(net_value)
        elif subtract_vat is False:
            updates.append('net_value = %s')
            params.append(None)

        if not updates:
            return False

        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(invoice_id)

        query = f"UPDATE invoices SET {', '.join(updates)} WHERE id = %s"

        try:
            updated = self.execute(query, params) > 0
            if updated:
                clear_invoices_cache()
            return updated
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                raise ValueError("Invoice number already exists in database")
            raise

    def check_number_exists(self, invoice_number, exclude_id=None):
        """Check if invoice number already exists in database."""
        if exclude_id:
            row = self.query_one('''
                SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
                FROM invoices WHERE invoice_number = %s AND id != %s
            ''', (invoice_number, exclude_id))
        else:
            row = self.query_one('''
                SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
                FROM invoices WHERE invoice_number = %s
            ''', (invoice_number,))

        if row:
            return {'exists': True, 'invoice': row}
        return {'exists': False, 'invoice': None}

    def search(self, query, filters=None):
        """Search invoices by supplier, invoice number, or value."""
        filters = filters or {}

        words = [w.strip() for w in query.split() if w.strip()]
        if not words:
            return []

        def parse_numeric(word):
            cleaned = word.replace(' ', '').replace('.', '').replace(',', '.')
            try:
                return float(cleaned)
            except ValueError:
                return None

        search_conditions = []
        params = []
        for word in words:
            term = f'%{word}%'
            numeric_val = parse_numeric(word)
            if numeric_val is not None:
                search_conditions.append('(i.supplier ILIKE %s OR i.invoice_number ILIKE %s OR i.comment ILIKE %s OR ABS(i.invoice_value - %s) < 0.01)')
                params.extend([term, term, term, numeric_val])
            else:
                search_conditions.append('(i.supplier ILIKE %s OR i.invoice_number ILIKE %s OR i.comment ILIKE %s)')
                params.extend([term, term, term])

        company = filters.get('company')
        department = filters.get('department')
        subdepartment = filters.get('subdepartment')
        brand = filters.get('brand')

        if company or department or subdepartment or brand:
            base_query = 'SELECT DISTINCT i.* FROM invoices i JOIN allocations a ON a.invoice_id = i.id'
        else:
            base_query = 'SELECT DISTINCT i.* FROM invoices i'

        filter_conditions = ['i.deleted_at IS NULL']

        if company:
            filter_conditions.append('a.company = %s')
            params.append(company)
        if department:
            filter_conditions.append('a.department = %s')
            params.append(department)
        if subdepartment:
            filter_conditions.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            filter_conditions.append('a.brand = %s')
            params.append(brand)

        start_date = filters.get('start_date')
        end_date = filters.get('end_date')
        if start_date:
            filter_conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            filter_conditions.append('i.invoice_date <= %s')
            params.append(end_date)

        f_status = filters.get('status')
        f_payment_status = filters.get('payment_status')
        if f_status:
            filter_conditions.append('i.status = %s')
            params.append(f_status)
        if f_payment_status:
            filter_conditions.append('i.payment_status = %s')
            params.append(f_payment_status)

        all_conditions = search_conditions + filter_conditions
        where_clause = ' AND '.join(all_conditions)

        return self.query_all(f'''
            {base_query}
            WHERE {where_clause}
            ORDER BY i.created_at DESC
            LIMIT 50
        ''', params)
