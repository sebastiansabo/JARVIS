"""CO balance data access layer."""

from core.base_repository import BaseRepository


class CoBalanceRepository(BaseRepository):
    """CRUD for sincron_co_balance + sincron_co_import_runs."""

    # ── Upsert ──

    def upsert(self, *, year, company_name, cnp, nume, prenume, nr_contract,
               data_incepere_contract, departament,
               carry_prev_year, carry_two_years_ago, annual_cim,
               seniority_bonus, manual_adjustment,
               mapped_jarvis_user_id, source_file, imported_by):
        """Insert-or-update a CO balance row keyed by (year, company_name, cnp)."""
        return self.execute(
            """
            INSERT INTO sincron_co_balance (
                year, company_name, cnp, nume, prenume, nr_contract,
                data_incepere_contract, departament,
                carry_prev_year, carry_two_years_ago, annual_cim,
                seniority_bonus, manual_adjustment,
                mapped_jarvis_user_id, source_file, imported_by, imported_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (year, company_name, cnp) DO UPDATE SET
                nume = EXCLUDED.nume,
                prenume = EXCLUDED.prenume,
                nr_contract = EXCLUDED.nr_contract,
                data_incepere_contract = EXCLUDED.data_incepere_contract,
                departament = EXCLUDED.departament,
                carry_prev_year = EXCLUDED.carry_prev_year,
                carry_two_years_ago = EXCLUDED.carry_two_years_ago,
                annual_cim = EXCLUDED.annual_cim,
                seniority_bonus = EXCLUDED.seniority_bonus,
                manual_adjustment = EXCLUDED.manual_adjustment,
                mapped_jarvis_user_id = EXCLUDED.mapped_jarvis_user_id,
                source_file = EXCLUDED.source_file,
                imported_by = EXCLUDED.imported_by,
                imported_at = NOW()
            RETURNING id
            """,
            (year, company_name, cnp, nume, prenume, nr_contract,
             data_incepere_contract, departament,
             carry_prev_year, carry_two_years_ago, annual_cim,
             seniority_bonus, manual_adjustment,
             mapped_jarvis_user_id, source_file, imported_by),
            returning=True,
        )

    # ── Read ──

    def get_for_user(self, user_id, year):
        return self.query_one(
            """
            SELECT * FROM sincron_co_balance
            WHERE mapped_jarvis_user_id = %s AND year = %s
            ORDER BY imported_at DESC LIMIT 1
            """,
            (user_id, year),
        )

    def get_for_year(self, year):
        """All rows for a year keyed by mapped_jarvis_user_id (NULL ignored).
        NOTE: multi-company employees keep only last row — use get_all_for_year() for full list.
        """
        rows = self.query_all(
            """
            SELECT
                mapped_jarvis_user_id AS user_id,
                year, company_name, cnp, nume, prenume, departament,
                carry_prev_year, carry_two_years_ago,
                annual_cim, seniority_bonus, manual_adjustment,
                total_available
            FROM sincron_co_balance
            WHERE year = %s AND mapped_jarvis_user_id IS NOT NULL
            """,
            (year,),
        )
        return {r['user_id']: r for r in rows}

    def get_all_for_year(self, year):
        """All CO balance rows for a year (one per user+company). Returns a list."""
        return self.query_all(
            """
            SELECT
                id, mapped_jarvis_user_id AS user_id,
                year, company_name, cnp, nume, prenume, departament,
                carry_prev_year, carry_two_years_ago,
                annual_cim, seniority_bonus, manual_adjustment,
                total_available
            FROM sincron_co_balance
            WHERE year = %s AND mapped_jarvis_user_id IS NOT NULL
            ORDER BY nume, prenume, company_name
            """,
            (year,),
        )

    def count_for_year(self, year):
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM sincron_co_balance WHERE year = %s",
            (year,),
        )
        return int(row['n']) if row else 0

    def unmatched_for_year(self, year):
        return self.query_all(
            """
            SELECT id, year, company_name, cnp, nume, prenume, nr_contract,
                   data_incepere_contract, departament, total_available
            FROM sincron_co_balance
            WHERE year = %s AND mapped_jarvis_user_id IS NULL
            ORDER BY company_name, nume, prenume
            """,
            (year,),
        )

    def assign_user(self, row_id, user_id):
        """Manually map a CO balance row to a JARVIS user."""
        return self.execute(
            """
            UPDATE sincron_co_balance
            SET mapped_jarvis_user_id = %s
            WHERE id = %s
            RETURNING id
            """,
            (user_id, row_id),
            returning=True,
        )

    def adjust_manual(self, user_id, year, delta):
        """Atomically adjust manual_adjustment by delta (negative to deduct)."""
        return self.execute(
            """
            UPDATE sincron_co_balance
            SET manual_adjustment = manual_adjustment + %s
            WHERE mapped_jarvis_user_id = %s AND year = %s
            RETURNING id, manual_adjustment
            """,
            (delta, user_id, year),
            returning=True,
        )

    def get_used_ytd_by_user(self, year):
        """Σ of Sincron CO days-unit entries per JARVIS user, for a given year."""
        rows = self.query_all(
            """
            SELECT se.mapped_jarvis_user_id AS user_id,
                   COALESCE(SUM(st.value), 0) AS used_ytd
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON st.sincron_employee_id = se.sincron_employee_id
             AND st.company_name        = se.company_name
            WHERE st.year       = %s
              AND st.short_code = 'CO'
              AND st.unit       = 'day'
              AND se.mapped_jarvis_user_id IS NOT NULL
            GROUP BY se.mapped_jarvis_user_id
            """,
            (year,),
        )
        return {r['user_id']: float(r['used_ytd'] or 0) for r in rows}

    def get_for_year_by_company(self, year):
        """All CO balance rows keyed by (user_id → {company_name → row})."""
        rows = self.query_all(
            """
            SELECT mapped_jarvis_user_id AS user_id, company_name,
                   carry_prev_year, total_available
            FROM sincron_co_balance
            WHERE year = %s AND mapped_jarvis_user_id IS NOT NULL
            """,
            (year,),
        )
        result = {}
        for r in rows:
            result.setdefault(r['user_id'], {})[r['company_name']] = r
        return result

    def get_used_ytd_by_user_company(self, year):
        """CO used YTD grouped by (user_id → {company_name → used_ytd})."""
        rows = self.query_all(
            """
            SELECT se.mapped_jarvis_user_id AS user_id,
                   se.company_name,
                   COALESCE(SUM(st.value), 0) AS used_ytd
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON st.sincron_employee_id = se.sincron_employee_id
             AND st.company_name        = se.company_name
            WHERE st.year       = %s
              AND st.short_code = 'CO'
              AND st.unit       = 'day'
              AND se.mapped_jarvis_user_id IS NOT NULL
            GROUP BY se.mapped_jarvis_user_id, se.company_name
            """,
            (year,),
        )
        result = {}
        for r in rows:
            result.setdefault(r['user_id'], {})[r['company_name']] = float(r['used_ytd'] or 0)
        return result

    # ── Delete ──

    def delete_rows(self, row_ids):
        """Delete CO balance rows by their database IDs."""
        if not row_ids:
            return 0
        return self.execute(
            "DELETE FROM sincron_co_balance WHERE id IN %s",
            (tuple(row_ids),),
        )

    # ── Import runs ──

    def create_import_run(self, run_id, year, source_file, imported_by):
        return self.execute(
            """
            INSERT INTO sincron_co_import_runs
                (run_id, year, source_file, status, imported_by)
            VALUES (%s, %s, %s, 'running', %s)
            RETURNING id
            """,
            (run_id, year, source_file, imported_by),
            returning=True,
        )

    def finish_import_run(self, run_id, *, status, rows_total, rows_matched,
                          rows_unmatched, companies, error_message=None):
        return self.execute(
            """
            UPDATE sincron_co_import_runs
            SET status = %s,
                rows_total = %s,
                rows_matched = %s,
                rows_unmatched = %s,
                companies = %s,
                error_message = %s,
                finished_at = NOW()
            WHERE run_id = %s
            """,
            (status, rows_total, rows_matched, rows_unmatched,
             companies, error_message, run_id),
        )

    def get_import_run(self, run_id):
        return self.query_one(
            "SELECT * FROM sincron_co_import_runs WHERE run_id = %s",
            (run_id,),
        )

    def list_import_runs(self, limit=20):
        return self.query_all(
            """
            SELECT run_id, year, source_file, status, rows_total, rows_matched,
                   rows_unmatched, companies, error_message,
                   started_at, finished_at
            FROM sincron_co_import_runs
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        )
