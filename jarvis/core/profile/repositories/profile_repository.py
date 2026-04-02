"""Profile Repository.

Cross-domain aggregation queries for user profile data:
invoices (by responsible), HR event bonuses, and activity log.
"""
from typing import Optional

from core.base_repository import BaseRepository
from database import dict_from_row


class ProfileRepository(BaseRepository):
    """Read-only aggregation queries for the user profile page."""

    # ------------------------------------------------------------------
    # Organigram department filter helper
    # ------------------------------------------------------------------

    @staticmethod
    def _build_org_filter(cursor, user_id: int) -> tuple[str, list]:
        """Build SQL clause for invoices visible via L0-L5 organigram.

        Returns (sql_fragment, params) — an OR clause for department scope.
        L0 (company_responsables): all invoices for that company.
        L1+ (structure_node responsable): invoices matching the node name
             or any descendant node name (department/subdepartment).
        If user has NO organigram assignments, returns empty (no filter).
        """
        # L0: company responsable assignments
        cursor.execute('''
            SELECT c.id as company_id, c.company
            FROM company_responsables cr
            JOIN companies c ON cr.company_id = c.id
            WHERE cr.user_id = %s
        ''', (user_id,))
        l0_rows = cursor.fetchall()
        l0_company_ids = {r['company_id'] for r in l0_rows}

        # L1-L5: nodes where user is responsable + all descendants (recursive)
        cursor.execute('''
            WITH RECURSIVE resp_nodes AS (
                SELECT sn.id, sn.name, sn.level, sn.company_id
                FROM structure_node_members snm
                JOIN structure_nodes sn ON snm.node_id = sn.id
                WHERE snm.user_id = %s AND snm.role = 'responsable'
            ),
            descendants AS (
                SELECT id, name, level, company_id FROM resp_nodes
                UNION ALL
                SELECT sn.id, sn.name, sn.level, sn.company_id
                FROM structure_nodes sn
                JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT d.name, d.level, d.company_id, c.company
            FROM descendants d
            JOIN companies c ON d.company_id = c.id
        ''', (user_id,))
        node_rows = cursor.fetchall()

        if not node_rows and not l0_rows:
            return '', []

        conditions = []
        params = []

        # L0: all invoices for the company
        l0_companies = {r['company'] for r in l0_rows}
        for comp in l0_companies:
            conditions.append('a.company = %s')
            params.append(comp)

        # Group descendant node names by company (skip L0-covered companies)
        from collections import defaultdict
        company_names = defaultdict(set)
        for nr in node_rows:
            if nr['company_id'] in l0_company_ids:
                continue
            company_names[nr['company']].add(nr['name'].lower())

        for comp, names in company_names.items():
            name_list = list(names)
            placeholders = ','.join(['%s'] * len(name_list))
            # Match department OR subdepartment against any node in the tree
            conditions.append(
                f'(a.company = %s AND (LOWER(a.department) IN ({placeholders})'
                f' OR LOWER(COALESCE(a.subdepartment, \'\')) IN ({placeholders})))'
            )
            params.append(comp)
            params.extend(name_list)
            params.extend(name_list)

        if not conditions:
            return '', []

        return '(' + ' OR '.join(conditions) + ')', params

    # ------------------------------------------------------------------
    # Invoice visibility check (same org-scope as list)
    # ------------------------------------------------------------------

    def is_invoice_visible_to_user(self, user_id: int, invoice_id: int) -> bool:
        """Check if a given invoice is visible to the user via org-scope or direct responsibility."""
        def _work(cursor):
            org_sql, org_params = self._build_org_filter(cursor, user_id)

            if org_sql:
                scope = org_sql
                scope_params = org_params
            else:
                scope = '(a.responsible_user_id = %s OR (a.responsible_user_id IS NULL AND LOWER(a.responsible) = (SELECT LOWER(name) FROM users WHERE id = %s)))'
                scope_params = [user_id, user_id]

            cursor.execute(f'''
                SELECT 1 FROM invoices i
                INNER JOIN allocations a ON i.id = a.invoice_id
                WHERE i.id = %s AND {scope} AND i.deleted_at IS NULL
                LIMIT 1
            ''', [invoice_id] + list(scope_params))
            return cursor.fetchone() is not None
        return self.execute_many(_work)

    # ------------------------------------------------------------------
    # User invoices (org-scope based: L0>L1>L2>L3>L4, fallback to own)
    # ------------------------------------------------------------------

    def get_user_invoices_by_responsible_name(
        self,
        user_email: str,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        department: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get invoices visible to the user based on L0-L5 org scope.
        Fallback: if no org assignments, show only directly-responsible invoices.
        """
        def _work(cursor):
            cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(%s)', [user_email])
            user_row = cursor.fetchone()
            if not user_row:
                return []

            user_id = user_row['id']
            org_sql, org_params = self._build_org_filter(cursor, user_id)

            if org_sql:
                # Org scope: L0 sees all company, L1 sees dept+descendants, etc.
                scope = org_sql
                scope_params = org_params
            else:
                # No org assignments: show only own invoices
                scope = '(a.responsible_user_id = %s OR (a.responsible_user_id IS NULL AND LOWER(a.responsible) = (SELECT LOWER(name) FROM users WHERE id = %s)))'
                scope_params = [user_id, user_id]

            # Build optional filter clauses
            extra_where = ''
            params = list(scope_params)

            if status:
                extra_where += ' AND i.status = %s'
                params.append(status)
            if start_date:
                extra_where += ' AND i.invoice_date >= %s'
                params.append(start_date)
            if end_date:
                extra_where += ' AND i.invoice_date <= %s'
                params.append(end_date)
            if search:
                extra_where += ' AND (i.invoice_number ILIKE %s OR i.supplier ILIKE %s)'
                search_pattern = f'%{search}%'
                params.extend([search_pattern, search_pattern])
            if department:
                extra_where += ' AND LOWER(a.department) = LOWER(%s)'
                params.append(department)

            # Use CTE to paginate distinct invoices, then aggregate allocations
            query = f'''
                WITH filtered_invoices AS (
                    SELECT DISTINCT i.id
                    FROM invoices i
                    INNER JOIN allocations a ON i.id = a.invoice_id
                    WHERE {scope} AND i.deleted_at IS NULL {extra_where}
                    ORDER BY i.id DESC
                    LIMIT %s OFFSET %s
                )
                SELECT
                    i.id, i.invoice_number, i.invoice_date, i.invoice_value,
                    i.currency, i.supplier, i.status, i.drive_link, i.comment,
                    i.created_at, i.updated_at, i.payment_status,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'id', a.id,
                                'company', a.company,
                                'brand', a.brand,
                                'department', a.department,
                                'subdepartment', a.subdepartment,
                                'allocation_percent', a.allocation_percent,
                                'allocation_value', a.allocation_value,
                                'responsible', a.responsible
                            )
                        ) FILTER (WHERE a.id IS NOT NULL),
                        '[]'::json
                    ) as allocations
                FROM filtered_invoices fi
                JOIN invoices i ON i.id = fi.id
                LEFT JOIN allocations a ON a.invoice_id = i.id
                GROUP BY i.id
                ORDER BY i.invoice_date DESC
            '''
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = []
            for row in cursor.fetchall():
                d = dict_from_row(dict(row))
                # For backwards compat: set top-level fields from first allocation
                allocs = d.get('allocations') or []
                if allocs:
                    first = allocs[0]
                    d['company'] = first.get('company')
                    d['brand'] = first.get('brand')
                    d['department'] = first.get('department')
                    d['subdepartment'] = first.get('subdepartment')
                    d['allocation_percent'] = first.get('allocation_percent')
                    d['allocation_value'] = first.get('allocation_value')
                rows.append(d)
            return rows
        return self.execute_many(_work)

    def get_user_invoices_count(
        self,
        user_email: str,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        department: Optional[str] = None,
    ) -> int:
        """Count invoices visible via L0-L5 org scope (fallback: own)."""
        def _work(cursor):
            cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(%s)', [user_email])
            user_row = cursor.fetchone()
            if not user_row:
                return 0

            user_id = user_row['id']
            org_sql, org_params = self._build_org_filter(cursor, user_id)

            if org_sql:
                scope = org_sql
                scope_params = org_params
            else:
                scope = '(a.responsible_user_id = %s OR (a.responsible_user_id IS NULL AND LOWER(a.responsible) = (SELECT LOWER(name) FROM users WHERE id = %s)))'
                scope_params = [user_id, user_id]

            query = f'''
                SELECT COUNT(DISTINCT i.id) as count
                FROM invoices i
                INNER JOIN allocations a ON i.id = a.invoice_id
                WHERE {scope}
                AND i.deleted_at IS NULL
            '''
            params = list(scope_params)

            if status:
                query += ' AND i.status = %s'
                params.append(status)
            if start_date:
                query += ' AND i.invoice_date >= %s'
                params.append(start_date)
            if end_date:
                query += ' AND i.invoice_date <= %s'
                params.append(end_date)
            if search:
                query += ' AND (i.invoice_number ILIKE %s OR i.supplier ILIKE %s)'
                search_pattern = f'%{search}%'
                params.extend([search_pattern, search_pattern])
            if department:
                query += ' AND LOWER(a.department) = LOWER(%s)'
                params.append(department)

            cursor.execute(query, params)
            row = cursor.fetchone()
            return row['count'] if row else 0
        return self.execute_many(_work)

    def get_user_invoices_summary(self, user_email: str) -> dict:
        """Get invoice summary stats via L0-L5 org scope (fallback: own)."""
        def _work(cursor):
            cursor.execute('SELECT id FROM users WHERE LOWER(email) = LOWER(%s)', [user_email])
            user_row = cursor.fetchone()
            if not user_row:
                return {'total': 0, 'total_value': 0, 'by_status': {}}

            user_id = user_row['id']
            org_sql, org_params = self._build_org_filter(cursor, user_id)

            if org_sql:
                base_where = org_sql
                base_params = org_params
            else:
                base_where = '(a.responsible_user_id = %s OR (a.responsible_user_id IS NULL AND LOWER(a.responsible) = (SELECT LOWER(name) FROM users WHERE id = %s)))'
                base_params = [user_id, user_id]

            cursor.execute(f'''
                SELECT i.status, COUNT(DISTINCT i.id) as count
                FROM invoices i
                INNER JOIN allocations a ON i.id = a.invoice_id
                WHERE {base_where} AND i.deleted_at IS NULL
                GROUP BY i.status
            ''', base_params)

            by_status = {}
            for row in cursor.fetchall():
                by_status[row['status'] or 'unknown'] = row['count']

            cursor.execute(f'''
                SELECT COUNT(DISTINCT i.id) as total, COALESCE(SUM(DISTINCT i.invoice_value), 0) as total_value
                FROM invoices i
                INNER JOIN allocations a ON i.id = a.invoice_id
                WHERE {base_where} AND i.deleted_at IS NULL
            ''', base_params)

            totals = cursor.fetchone()

            return {
                'total': totals['total'] if totals else 0,
                'total_value': float(totals['total_value']) if totals else 0,
                'by_status': by_status,
            }
        return self.execute_many(_work)

    # ------------------------------------------------------------------
    # HR event bonuses
    # ------------------------------------------------------------------

    def get_user_event_bonuses(
        self,
        user_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """Get HR event bonuses for a user."""
        def _work(cursor):
            query = '''
                SELECT
                    eb.id, eb.year, eb.month, eb.bonus_days, eb.hours_free,
                    eb.bonus_net, eb.details, eb.allocation_month,
                    eb.participation_start, eb.participation_end,
                    eb.created_at, eb.updated_at,
                    e.name as event_name, e.start_date, e.end_date,
                    e.company, e.brand
                FROM hr.event_bonuses eb
                INNER JOIN hr.events e ON eb.event_id = e.id
                WHERE eb.user_id = %s
            '''
            params = [user_id]

            if year:
                query += ' AND eb.year = %s'
                params.append(year)
            if month:
                query += ' AND eb.month = %s'
                params.append(month)
            if search:
                query += ' AND (e.name ILIKE %s OR e.company ILIKE %s)'
                search_pattern = f'%{search}%'
                params.extend([search_pattern, search_pattern])

            query += ' ORDER BY eb.year DESC, eb.month DESC LIMIT %s OFFSET %s'
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict_from_row(dict(row)) for row in cursor.fetchall()]
        return self.execute_many(_work)

    def get_user_event_bonuses_summary(self, user_id: int) -> dict:
        """Get summary of HR event bonuses for a user."""
        row = self.query_one('''
            SELECT
                COUNT(*) as total_bonuses,
                COALESCE(SUM(eb.bonus_net), 0) as total_amount,
                COUNT(DISTINCT eb.event_id) as events_count
            FROM hr.event_bonuses eb
            WHERE eb.user_id = %s
        ''', (user_id,))
        if row:
            return {
                'total_bonuses': row['total_bonuses'],
                'total_amount': float(row['total_amount']),
                'events_count': row['events_count'],
            }
        return {'total_bonuses': 0, 'total_amount': 0, 'events_count': 0}

    def get_user_event_bonuses_count(
        self,
        user_id: int,
        year: Optional[int] = None,
        month: Optional[int] = None,
        search: Optional[str] = None,
    ) -> int:
        """Get count of HR event bonuses for a user with filters."""
        def _work(cursor):
            query = '''
                SELECT COUNT(*) as count
                FROM hr.event_bonuses eb
                INNER JOIN hr.events e ON eb.event_id = e.id
                WHERE eb.user_id = %s
            '''
            params = [user_id]

            if year:
                query += ' AND eb.year = %s'
                params.append(year)
            if month:
                query += ' AND eb.month = %s'
                params.append(month)
            if search:
                query += ' AND (e.name ILIKE %s OR e.company ILIKE %s)'
                search_pattern = f'%{search}%'
                params.extend([search_pattern, search_pattern])

            cursor.execute(query, params)
            row = cursor.fetchone()
            return row['count'] if row else 0
        return self.execute_many(_work)

    # ------------------------------------------------------------------
    # User activity log
    # ------------------------------------------------------------------

    def get_user_activity(
        self,
        user_id: int,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get activity log for a user."""
        def _work(cursor):
            query = '''
                SELECT id, event_type, details, ip_address, user_agent, created_at
                FROM user_events
                WHERE user_id = %s
            '''
            params = [user_id]

            if event_type:
                query += ' AND event_type = %s'
                params.append(event_type)

            query += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict_from_row(dict(row)) for row in cursor.fetchall()]
        return self.execute_many(_work)

    def get_user_activity_count(self, user_id: int) -> int:
        """Count activity events for a user."""
        row = self.query_one('''
            SELECT COUNT(*) as count
            FROM user_events
            WHERE user_id = %s
        ''', (user_id,))
        return row['count'] if row else 0
