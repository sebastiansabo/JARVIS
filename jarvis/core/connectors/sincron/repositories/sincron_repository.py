"""Sincron connector data access — employees and timesheets."""

from core.base_repository import BaseRepository


class SincronRepository(BaseRepository):
    """CRUD for sincron_employees and sincron_timesheets."""

    # ── Employee operations ──

    def upsert_employee(self, sincron_employee_id, company_name, nume, prenume,
                        cnp=None, id_contract=None, nr_contract=None,
                        data_incepere_contract=None, norma_lucru=None,
                        norma_lucru_time=None, schedule_start=None,
                        schedule_end=None, lunch_break_minutes=None):
        """Insert or update a Sincron employee record."""
        return self.execute('''
            INSERT INTO sincron_employees
                (sincron_employee_id, company_name, nume, prenume, cnp,
                 id_contract, nr_contract, data_incepere_contract,
                 norma_lucru, norma_lucru_time, schedule_start, schedule_end,
                 lunch_break_minutes, last_synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sincron_employee_id, company_name) DO UPDATE SET
                nume = EXCLUDED.nume,
                prenume = EXCLUDED.prenume,
                cnp = EXCLUDED.cnp,
                id_contract = EXCLUDED.id_contract,
                nr_contract = EXCLUDED.nr_contract,
                data_incepere_contract = EXCLUDED.data_incepere_contract,
                norma_lucru = EXCLUDED.norma_lucru,
                norma_lucru_time = EXCLUDED.norma_lucru_time,
                schedule_start = EXCLUDED.schedule_start,
                schedule_end = EXCLUDED.schedule_end,
                lunch_break_minutes = EXCLUDED.lunch_break_minutes,
                is_active = TRUE,
                contract_status = NULL,
                last_synced_at = NOW(),
                updated_at = NOW()
            RETURNING id, sincron_employee_id, company_name, mapped_jarvis_user_id
        ''', (sincron_employee_id, company_name, nume, prenume, cnp,
              id_contract, nr_contract, data_incepere_contract,
              norma_lucru, norma_lucru_time, schedule_start, schedule_end,
              lunch_break_minutes), returning=True)

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
            ORDER BY se.id ASC
            LIMIT 1
        ''', (jarvis_user_id,))

    def get_all_employees_by_jarvis_id(self, jarvis_user_id):
        """Get ALL Sincron employee entries mapped to a JARVIS user (multi-company)."""
        return self.query_all('''
            SELECT se.id, se.sincron_employee_id, se.company_name,
                   se.nume, se.prenume, se.id_contract, se.nr_contract,
                   se.data_incepere_contract, se.mapped_jarvis_user_id,
                   se.mapping_method, se.mapping_confidence,
                   se.norma_lucru, se.norma_lucru_time,
                   se.schedule_start, se.schedule_end, se.lunch_break_minutes,
                   se.last_synced_at
            FROM sincron_employees se
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
            ORDER BY se.company_name
        ''', (jarvis_user_id,))

    def get_combined_schedules_for_biostar(self):
        """Get combined schedule data per JARVIS user for BioStar backfill.

        The norm is SPLIT across companies (total never exceeds 8h).
        Uses primary company (highest norma_lucru) for schedule times/lunch.
        """
        return self.query_all('''
            WITH ranked AS (
                SELECT se.mapped_jarvis_user_id,
                       se.norma_lucru,
                       se.schedule_start,
                       se.schedule_end,
                       COALESCE(se.lunch_break_minutes, 0) AS lunch_break_minutes,
                       ROW_NUMBER() OVER (
                           PARTITION BY se.mapped_jarvis_user_id
                           ORDER BY se.norma_lucru DESC
                       ) AS rn
                FROM sincron_employees se
                WHERE se.mapped_jarvis_user_id IS NOT NULL
                  AND se.is_active = TRUE
                  AND se.norma_lucru IS NOT NULL
            ),
            totals AS (
                SELECT mapped_jarvis_user_id,
                       LEAST(SUM(norma_lucru), 8)::NUMERIC(5,1) AS total_working_hours
                FROM ranked
                GROUP BY mapped_jarvis_user_id
            )
            SELECT t.mapped_jarvis_user_id,
                   t.total_working_hours,
                   r.schedule_start AS combined_start,
                   r.schedule_end AS combined_end,
                   r.lunch_break_minutes AS total_lunch
            FROM totals t
            JOIN ranked r ON r.mapped_jarvis_user_id = t.mapped_jarvis_user_id AND r.rn = 1
        ''')

    def get_all_company_norms(self):
        """Get per-company norm breakdown for all mapped active employees."""
        return self.query_all('''
            SELECT mapped_jarvis_user_id, company_name,
                   norma_lucru, schedule_start, schedule_end, lunch_break_minutes
            FROM sincron_employees
            WHERE mapped_jarvis_user_id IS NOT NULL
              AND is_active = TRUE
              AND norma_lucru IS NOT NULL
            ORDER BY mapped_jarvis_user_id, norma_lucru DESC
        ''')

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

    def get_employee(self, sincron_employee_id, company_name):
        """Get a single Sincron employee by composite key."""
        return self.query_one('''
            SELECT id, sincron_employee_id, company_name, nume, prenume, cnp,
                   id_contract, nr_contract, data_incepere_contract,
                   mapped_jarvis_user_id, mapping_method, mapping_confidence,
                   is_active, last_synced_at
            FROM sincron_employees
            WHERE sincron_employee_id = %s AND company_name = %s
        ''', (sincron_employee_id, company_name))

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

    def get_active_employee_ids(self, company_name):
        """Get all active sincron_employee_ids for a company."""
        rows = self.query_all('''
            SELECT sincron_employee_id
            FROM sincron_employees
            WHERE company_name = %s AND is_active = TRUE
        ''', (company_name,))
        return {r['sincron_employee_id'] for r in rows}

    def deactivate_employees(self, company_name, sincron_employee_ids):
        """Mark employees as inactive (contract closed).

        Returns list of mapped_jarvis_user_id values (non-null) for
        cascading the deactivation to JARVIS users.
        """
        if not sincron_employee_ids:
            return []
        ids_list = list(sincron_employee_ids)
        rows = self.query_all('''
            UPDATE sincron_employees
            SET is_active = FALSE,
                contract_status = 'closed',
                updated_at = NOW()
            WHERE company_name = %s
              AND sincron_employee_id = ANY(%s)
              AND is_active = TRUE
            RETURNING mapped_jarvis_user_id
        ''', (company_name, ids_list))
        return [r['mapped_jarvis_user_id'] for r in rows
                if r.get('mapped_jarvis_user_id')]

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
                  AND COALESCE(u.contract_status, 'active') != 'closed'
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
                  AND COALESCE(u.contract_status, 'active') != 'closed'
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
                  AND COALESCE(u.contract_status, 'active') != 'closed'
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
                             day, short_code, short_code_en, unit, value,
                             program_in=None, program_out=None, program_break=None):
        """Insert or update a single timesheet day activity."""
        return self.execute('''
            INSERT INTO sincron_timesheets
                (sincron_employee_id, company_name, year, month, day,
                 short_code, short_code_en, unit, value,
                 program_in, program_out, program_break, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sincron_employee_id, company_name, day, short_code) DO UPDATE SET
                short_code_en = EXCLUDED.short_code_en,
                unit = EXCLUDED.unit,
                value = EXCLUDED.value,
                program_in = EXCLUDED.program_in,
                program_out = EXCLUDED.program_out,
                program_break = EXCLUDED.program_break,
                synced_at = NOW()
        ''', (sincron_employee_id, company_name, year, month, day,
              short_code, short_code_en, unit, value,
              program_in, program_out, program_break))

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

    # ── Schedule history ──

    def upsert_schedule_snapshot(self, sincron_employee_id, company_name, year, month,
                                 norma_lucru=None, norma_lucru_time=None,
                                 schedule_start=None, schedule_end=None,
                                 lunch_break_minutes=None):
        """Capture a monthly schedule snapshot for an employee."""
        return self.execute('''
            INSERT INTO sincron_schedule_history
                (sincron_employee_id, company_name, year, month,
                 norma_lucru, norma_lucru_time, schedule_start, schedule_end,
                 lunch_break_minutes, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sincron_employee_id, company_name, year, month) DO UPDATE SET
                norma_lucru = EXCLUDED.norma_lucru,
                norma_lucru_time = EXCLUDED.norma_lucru_time,
                schedule_start = EXCLUDED.schedule_start,
                schedule_end = EXCLUDED.schedule_end,
                lunch_break_minutes = EXCLUDED.lunch_break_minutes,
                synced_at = NOW()
        ''', (sincron_employee_id, company_name, year, month,
              norma_lucru, norma_lucru_time, schedule_start, schedule_end,
              lunch_break_minutes))

    def get_schedule_history_by_jarvis_id(self, jarvis_user_id, year, month):
        """Get schedule snapshot for a JARVIS user for a specific month."""
        return self.query_all('''
            SELECT sh.sincron_employee_id, sh.company_name, sh.year, sh.month,
                   sh.norma_lucru, sh.norma_lucru_time,
                   sh.schedule_start, sh.schedule_end, sh.lunch_break_minutes,
                   se.nr_contract, se.data_incepere_contract
            FROM sincron_schedule_history sh
            JOIN sincron_employees se
              ON se.sincron_employee_id = sh.sincron_employee_id
              AND se.company_name = sh.company_name
            WHERE se.mapped_jarvis_user_id = %s
              AND sh.year = %s AND sh.month = %s
            ORDER BY sh.company_name
        ''', (jarvis_user_id, year, month))

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
            SELECT short_code, short_code_en, description, category, is_leave, created_at
            FROM sincron_activity_codes ORDER BY short_code
        ''')

    def get_leave_codes(self):
        """Return tuple of short_codes marked as leave in sincron_activity_codes."""
        rows = self.query_all('''
            SELECT short_code FROM sincron_activity_codes
            WHERE is_leave = TRUE ORDER BY short_code
        ''')
        return tuple(r['short_code'] for r in rows)

    def get_absence_codes(self):
        """Return tuple of all motivated-absence codes (leave + absence categories)."""
        rows = self.query_all('''
            SELECT short_code FROM sincron_activity_codes
            WHERE is_leave = TRUE OR category = 'absence'
            ORDER BY short_code
        ''')
        return tuple(r['short_code'] for r in rows)

    # ── JARVIS users for mapping dropdown (admin only — no CNP) ──

    def get_jarvis_users(self):
        """Get active JARVIS users for mapping (excludes sensitive PII)."""
        return self.query_all('''
            SELECT u.id, u.name, u.email, u.company, u.department
            FROM users u
            WHERE u.is_active = TRUE
            ORDER BY u.name
        ''')
