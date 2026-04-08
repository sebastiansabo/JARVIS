"""Sincron connector data access — employees and timesheets."""

from core.base_repository import BaseRepository


class SincronRepository(BaseRepository):
    """CRUD for sincron_employees and sincron_timesheets."""

    # ── Employee operations ──

    def upsert_employee(self, sincron_employee_id, company_name, nume, prenume,
                        cnp=None, id_contract=None, nr_contract=None,
                        data_incepere_contract=None):
        """Insert or update a Sincron employee record."""
        return self.execute('''
            INSERT INTO sincron_employees
                (sincron_employee_id, company_name, nume, prenume, cnp,
                 id_contract, nr_contract, data_incepere_contract, last_synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sincron_employee_id, company_name) DO UPDATE SET
                nume = EXCLUDED.nume,
                prenume = EXCLUDED.prenume,
                cnp = EXCLUDED.cnp,
                id_contract = EXCLUDED.id_contract,
                nr_contract = EXCLUDED.nr_contract,
                data_incepere_contract = EXCLUDED.data_incepere_contract,
                last_synced_at = NOW(),
                updated_at = NOW()
            RETURNING id, sincron_employee_id, company_name, mapped_jarvis_user_id
        ''', (sincron_employee_id, company_name, nume, prenume, cnp,
              id_contract, nr_contract, data_incepere_contract), returning=True)

    def get_all_employees(self, company_name=None, active_only=True):
        """Get all Sincron employees (CNP excluded from response)."""
        query = '''
            SELECT se.id, se.sincron_employee_id, se.company_name,
                   se.nume, se.prenume, se.id_contract, se.nr_contract,
                   se.data_incepere_contract, se.mapped_jarvis_user_id,
                   se.mapping_method, se.mapping_confidence, se.is_active,
                   se.last_synced_at, se.created_at, se.updated_at,
                   u.name AS mapped_jarvis_user_name
            FROM sincron_employees se
            LEFT JOIN users u ON u.id = se.mapped_jarvis_user_id
            WHERE 1=1
        '''
        params = []
        if active_only:
            query += ' AND se.is_active = TRUE'
        if company_name:
            query += ' AND se.company_name = %s'
            params.append(company_name)
        query += ' ORDER BY se.nume, se.prenume'
        return self.query_all(query, tuple(params))

    def get_employee_by_jarvis_id(self, jarvis_user_id):
        """Get Sincron employee mapped to a JARVIS user (CNP excluded)."""
        return self.query_one('''
            SELECT se.id, se.sincron_employee_id, se.company_name,
                   se.nume, se.prenume, se.id_contract, se.nr_contract,
                   se.data_incepere_contract, se.mapped_jarvis_user_id,
                   se.mapping_method, se.mapping_confidence,
                   se.last_synced_at,
                   u.name AS mapped_jarvis_user_name
            FROM sincron_employees se
            LEFT JOIN users u ON u.id = se.mapped_jarvis_user_id
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
            LIMIT 1
        ''', (jarvis_user_id,))

    def get_unmapped_employees(self):
        """Get employees not yet mapped to JARVIS users (CNP excluded)."""
        return self.query_all('''
            SELECT id, sincron_employee_id, company_name, nume, prenume,
                   id_contract, nr_contract, data_incepere_contract,
                   is_active, last_synced_at, created_at
            FROM sincron_employees
            WHERE mapped_jarvis_user_id IS NULL AND is_active = TRUE
            ORDER BY company_name, nume, prenume
        ''')

    def update_mapping(self, sincron_employee_id, company_name, jarvis_user_id, method='manual'):
        """Map a Sincron employee to a JARVIS user."""
        confidence = 100 if method == 'manual' else 90
        return self.execute('''
            UPDATE sincron_employees
            SET mapped_jarvis_user_id = %s, mapping_method = %s,
                mapping_confidence = %s, updated_at = NOW()
            WHERE sincron_employee_id = %s AND company_name = %s
        ''', (jarvis_user_id, method, confidence, sincron_employee_id, company_name))

    def remove_mapping(self, sincron_employee_id, company_name):
        """Remove JARVIS user mapping."""
        return self.execute('''
            UPDATE sincron_employees
            SET mapped_jarvis_user_id = NULL, mapping_method = NULL,
                mapping_confidence = 0, updated_at = NOW()
            WHERE sincron_employee_id = %s AND company_name = %s
        ''', (sincron_employee_id, company_name))

    def auto_map_by_cnp(self):
        """Auto-map unmapped employees by CNP match against users table."""
        def _work(cursor):
            cursor.execute('''
                UPDATE sincron_employees se
                SET mapped_jarvis_user_id = u.id,
                    mapping_method = 'cnp',
                    mapping_confidence = 100,
                    updated_at = NOW()
                FROM users u
                WHERE se.mapped_jarvis_user_id IS NULL
                  AND se.is_active = TRUE
                  AND se.cnp IS NOT NULL
                  AND u.cnp IS NOT NULL
                  AND REPLACE(se.cnp, 'x', '') != ''
                  AND u.is_active = TRUE
                  AND LOWER(TRIM(u.cnp)) = LOWER(TRIM(se.cnp))
            ''')
            return cursor.rowcount
        return self.execute_many(_work)

    def auto_map_by_name(self):
        """Auto-map unmapped employees by exact name match."""
        def _work(cursor):
            cursor.execute('''
                UPDATE sincron_employees se
                SET mapped_jarvis_user_id = u.id,
                    mapping_method = 'name',
                    mapping_confidence = 85,
                    updated_at = NOW()
                FROM users u
                WHERE se.mapped_jarvis_user_id IS NULL
                  AND se.is_active = TRUE
                  AND u.is_active = TRUE
                  AND LOWER(TRIM(u.name)) = LOWER(TRIM(se.nume || ' ' || se.prenume))
            ''')
            name_mapped = cursor.rowcount
            # Also try prenume + nume order
            cursor.execute('''
                UPDATE sincron_employees se
                SET mapped_jarvis_user_id = u.id,
                    mapping_method = 'name',
                    mapping_confidence = 80,
                    updated_at = NOW()
                FROM users u
                WHERE se.mapped_jarvis_user_id IS NULL
                  AND se.is_active = TRUE
                  AND u.is_active = TRUE
                  AND LOWER(TRIM(u.name)) = LOWER(TRIM(se.prenume || ' ' || se.nume))
            ''')
            return name_mapped + cursor.rowcount
        return self.execute_many(_work)

    def get_employee_stats(self):
        """Get employee counts."""
        row = self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE is_active) AS total,
                COUNT(*) FILTER (WHERE is_active AND mapped_jarvis_user_id IS NOT NULL) AS mapped,
                COUNT(*) FILTER (WHERE is_active AND mapped_jarvis_user_id IS NULL) AS unmapped,
                COUNT(DISTINCT company_name) FILTER (WHERE is_active) AS companies
            FROM sincron_employees
        ''')
        return row if row else {'total': 0, 'mapped': 0, 'unmapped': 0, 'companies': 0}

    # ── Timesheet operations ──

    def upsert_timesheet_day(self, sincron_employee_id, company_name, year, month,
                             day, short_code, short_code_en, unit, value):
        """Insert or update a single timesheet day activity."""
        return self.execute('''
            INSERT INTO sincron_timesheets
                (sincron_employee_id, company_name, year, month, day,
                 short_code, short_code_en, unit, value, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sincron_employee_id, company_name, day, short_code) DO UPDATE SET
                short_code_en = EXCLUDED.short_code_en,
                unit = EXCLUDED.unit,
                value = EXCLUDED.value,
                synced_at = NOW()
        ''', (sincron_employee_id, company_name, year, month, day,
              short_code, short_code_en, unit, value))

    def bulk_upsert_timesheet(self, records):
        """Bulk upsert timesheet records.

        records: list of tuples (sincron_employee_id, company_name, year, month,
                                  day, short_code, short_code_en, unit, value)
        """
        if not records:
            return 0

        def _work(cursor):
            from psycopg2.extras import execute_values
            execute_values(cursor, '''
                INSERT INTO sincron_timesheets
                    (sincron_employee_id, company_name, year, month, day,
                     short_code, short_code_en, unit, value, synced_at)
                VALUES %s
                ON CONFLICT (sincron_employee_id, company_name, day, short_code) DO UPDATE SET
                    short_code_en = EXCLUDED.short_code_en,
                    unit = EXCLUDED.unit,
                    value = EXCLUDED.value,
                    synced_at = NOW()
            ''', [r[:9] for r in records],
                template='(%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())')
            return cursor.rowcount
        return self.execute_many(_work)

    def get_employee_timesheet(self, sincron_employee_id, company_name, year, month):
        """Get monthly timesheet for one employee."""
        return self.query_all('''
            SELECT day, short_code, short_code_en, unit, value
            FROM sincron_timesheets
            WHERE sincron_employee_id = %s AND company_name = %s
              AND year = %s AND month = %s
            ORDER BY day, short_code
        ''', (sincron_employee_id, company_name, year, month))

    def get_timesheet_by_jarvis_user(self, jarvis_user_id, year, month):
        """Get monthly timesheet for a JARVIS user (via mapping)."""
        return self.query_all('''
            SELECT st.day, st.short_code, st.short_code_en, st.unit, st.value,
                   se.company_name, se.nume, se.prenume
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON se.sincron_employee_id = st.sincron_employee_id
              AND se.company_name = st.company_name
            WHERE se.mapped_jarvis_user_id = %s
              AND st.year = %s AND st.month = %s
            ORDER BY st.day, st.short_code
        ''', (jarvis_user_id, year, month))

    def get_timesheet_summary_by_jarvis_user(self, jarvis_user_id, year, month):
        """Get aggregated monthly summary — total hours by activity code."""
        return self.query_all('''
            SELECT st.short_code, st.short_code_en, st.unit,
                   SUM(st.value) AS total_value,
                   COUNT(*) AS day_count
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON se.sincron_employee_id = st.sincron_employee_id
              AND se.company_name = st.company_name
            WHERE se.mapped_jarvis_user_id = %s
              AND st.year = %s AND st.month = %s
            GROUP BY st.short_code, st.short_code_en, st.unit
            ORDER BY st.short_code
        ''', (jarvis_user_id, year, month))

    def get_team_timesheet_summary(self, jarvis_user_ids, year, month):
        """Get monthly summary for JARVIS users. Pass None for all mapped employees."""
        if jarvis_user_ids is not None and not jarvis_user_ids:
            return []
        if jarvis_user_ids is None:
            # All mapped employees (admin scope='all')
            return self.query_all('''
                SELECT se.mapped_jarvis_user_id, u.name AS employee_name,
                       se.company_name,
                       st.short_code, st.unit,
                       SUM(st.value) AS total_value,
                       COUNT(*) AS day_count
                FROM sincron_timesheets st
                JOIN sincron_employees se
                  ON se.sincron_employee_id = st.sincron_employee_id
                  AND se.company_name = st.company_name
                JOIN users u ON u.id = se.mapped_jarvis_user_id
                WHERE st.year = %s AND st.month = %s
                GROUP BY se.mapped_jarvis_user_id, u.name, se.company_name,
                         st.short_code, st.unit
                ORDER BY u.name, st.short_code
            ''', (year, month))
        return self.query_all('''
            SELECT se.mapped_jarvis_user_id, u.name AS employee_name,
                   se.company_name,
                   st.short_code, st.unit,
                   SUM(st.value) AS total_value,
                   COUNT(*) AS day_count
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON se.sincron_employee_id = st.sincron_employee_id
              AND se.company_name = st.company_name
            JOIN users u ON u.id = se.mapped_jarvis_user_id
            WHERE se.mapped_jarvis_user_id = ANY(%s)
              AND st.year = %s AND st.month = %s
            GROUP BY se.mapped_jarvis_user_id, u.name, se.company_name,
                     st.short_code, st.unit
            ORDER BY u.name, st.short_code
        ''', (jarvis_user_ids, year, month))

    def delete_month_timesheets(self, sincron_employee_id, company_name, year, month):
        """Delete all timesheet records for an employee/month (before re-sync)."""
        return self.execute('''
            DELETE FROM sincron_timesheets
            WHERE sincron_employee_id = %s AND company_name = %s
              AND year = %s AND month = %s
        ''', (sincron_employee_id, company_name, year, month))

    # ── Activity codes ──

    def upsert_activity_code(self, short_code, short_code_en=None, description=None, category=None):
        """Discover and store activity code from API responses."""
        return self.execute('''
            INSERT INTO sincron_activity_codes (short_code, short_code_en, description, category)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (short_code) DO UPDATE SET
                short_code_en = COALESCE(EXCLUDED.short_code_en, sincron_activity_codes.short_code_en),
                description = COALESCE(EXCLUDED.description, sincron_activity_codes.description)
        ''', (short_code, short_code_en, description, category))

    def get_activity_codes(self):
        """Get all known activity codes."""
        return self.query_all('''
            SELECT short_code, short_code_en, description, category, created_at
            FROM sincron_activity_codes ORDER BY short_code
        ''')

    # ── JARVIS users for mapping dropdown (admin only — no CNP) ──

    def get_jarvis_users(self):
        """Get active JARVIS users for mapping (excludes sensitive PII)."""
        return self.query_all('''
            SELECT u.id, u.name, u.email, u.company, u.department
            FROM users u
            WHERE u.is_active = TRUE
            ORDER BY u.name
        ''')
