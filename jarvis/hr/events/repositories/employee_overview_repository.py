"""Repository for Employee 360 overview — read-only aggregation queries."""
from core.base_repository import BaseRepository


class EmployeeOverviewRepository(BaseRepository):

    def get_biostar_mapping(self, user_id):
        """Return BioStar employee row for a JARVIS user, or None."""
        return self.query_one('''
            SELECT biostar_user_id, name AS user_name, email, phone, cnp,
                   user_group_name, (status = 'active') AS is_active,
                   lunch_break_minutes, working_hours,
                   schedule_start::text, schedule_end::text,
                   mapping_method, mapping_confidence
            FROM biostar_employees
            WHERE mapped_jarvis_user_id = %s
            LIMIT 1
        ''', (user_id,))

    def get_sincron_mapping(self, user_id):
        """Return Sincron employee row for a JARVIS user, or None."""
        return self.query_one('''
            SELECT sincron_employee_id, company_name, nume, prenume, cnp,
                   nr_contract, data_incepere_contract::text, mapping_method, mapping_confidence
            FROM sincron_employees
            WHERE mapped_jarvis_user_id = %s AND is_active = TRUE
            LIMIT 1
        ''', (user_id,))

    def get_connecteam_mapping(self, user_id):
        """Return Connecteam user row + submission count for a JARVIS user, or None."""
        return self.query_one('''
            SELECT cu.connecteam_user_id, cu.connecteam_user_name,
                   cu.connecteam_email, cu.mapping_method, cu.mapping_confidence,
                   (SELECT COUNT(*) FROM connecteam_form_submissions cfs
                    WHERE cfs.mapped_jarvis_user_id = %s) AS submission_count
            FROM connecteam_users cu
            WHERE cu.mapped_jarvis_user_id = %s AND cu.is_active = TRUE
            LIMIT 1
        ''', (user_id, user_id))

    def get_org_path(self, user_id):
        """Return {company, brand, department, subdepartment} for a user."""
        return self.query_one(
            'SELECT u.company, u.brand, u.department, u.subdepartment FROM users u WHERE u.id = %s',
            (user_id,)
        )

    def get_bonus_summary(self, user_id):
        """Return {bonus_count, total_bonus_days, total_bonus_net}."""
        return self.query_one('''
            SELECT COUNT(*) AS bonus_count,
                   COALESCE(SUM(bonus_days), 0) AS total_bonus_days,
                   COALESCE(SUM(bonus_net), 0) AS total_bonus_net
            FROM hr.event_bonuses WHERE user_id = %s
        ''', (user_id,))

    def get_form_submissions_count(self, user_id):
        """Return count of form submissions for a user."""
        row = self.query_one(
            'SELECT COUNT(*) AS submission_count FROM form_submissions WHERE respondent_user_id = %s',
            (user_id,)
        )
        return int(row['submission_count']) if row else 0

    def get_monthly_attendance_days(self, biostar_user_id, year, month):
        """Return distinct days with punches in a given month."""
        row = self.query_one('''
            SELECT COUNT(DISTINCT event_datetime::date) AS days_present
            FROM biostar_punch_logs
            WHERE biostar_user_id = %s
              AND EXTRACT(YEAR FROM event_datetime) = %s
              AND EXTRACT(MONTH FROM event_datetime) = %s
        ''', (biostar_user_id, year, month))
        return int(row['days_present']) if row else 0

    def get_monthly_hours_aggregate(self, biostar_user_id, year, month):
        """Return (total_span_hours, day_count) from first/last punch pairs in a month."""
        row = self.query_one('''
            SELECT SUM(span_h) AS total_h, COUNT(*) AS day_count FROM (
                SELECT (EXTRACT(EPOCH FROM MAX(event_datetime) - MIN(event_datetime)) / 3600) AS span_h
                FROM biostar_punch_logs
                WHERE biostar_user_id = %s
                  AND EXTRACT(YEAR FROM event_datetime) = %s
                  AND EXTRACT(MONTH FROM event_datetime) = %s
                GROUP BY event_datetime::date
                HAVING COUNT(*) >= 2
            ) sub
        ''', (biostar_user_id, year, month))
        if row:
            return float(row['total_h'] or 0), int(row['day_count'] or 0)
        return 0.0, 0

    def get_monthly_sincron_summary(self, sincron_employee_id, company_name, year, month):
        """Return dict of {short_code: {value, unit}} for a month's Sincron timesheet."""
        rows = self.query_all('''
            SELECT short_code, unit, SUM(value) AS total
            FROM sincron_timesheets
            WHERE sincron_employee_id = %s AND company_name = %s
              AND year = %s AND month = %s
            GROUP BY short_code, unit
            ORDER BY short_code
        ''', (sincron_employee_id, company_name, year, month))
        return {r['short_code']: {'value': float(r['total']), 'unit': r['unit']} for r in rows}

    def get_monthly_leave_permits(self, user_id, year, month):
        """Return (count, total_hours) of leave permits for a user in a month."""
        row = self.query_one('''
            SELECT COUNT(*) AS cnt, COALESCE(SUM(leave_hours), 0) AS total_h
            FROM connecteam_form_submissions
            WHERE mapped_jarvis_user_id = %s
              AND EXTRACT(YEAR FROM leave_date) = %s
              AND EXTRACT(MONTH FROM leave_date) = %s
        ''', (user_id, year, month))
        if row:
            return int(row['cnt']), round(float(row['total_h']), 1)
        return 0, 0.0

    def get_ytd_sincron_leave(self, sincron_employee_id, company_name, year):
        """Return dict of {short_code: {value, unit}} YTD leave codes from Sincron."""
        rows = self.query_all('''
            SELECT short_code, unit, SUM(value) AS total
            FROM sincron_timesheets
            WHERE sincron_employee_id = %s AND company_name = %s
              AND year = %s
              AND short_code IN ('CO', 'CM', 'CES', 'CIC', 'CMS', 'DLG')
            GROUP BY short_code, unit
            ORDER BY short_code
        ''', (sincron_employee_id, company_name, year))
        return {r['short_code']: {'value': float(r['total']), 'unit': r['unit']} for r in rows}

    def get_ytd_leave_permits(self, user_id, year):
        """Return (count, total_hours) of YTD leave permits for a user."""
        row = self.query_one('''
            SELECT COUNT(*) AS cnt, COALESCE(SUM(leave_hours), 0) AS total_h
            FROM connecteam_form_submissions
            WHERE mapped_jarvis_user_id = %s
              AND EXTRACT(YEAR FROM leave_date) = %s
        ''', (user_id, year))
        if row:
            return int(row['cnt']), round(float(row['total_h']), 1)
        return 0, 0.0

    def get_daily_punch_hours(self, biostar_user_id, year, month):
        """Return list of {day: date, span_h: float} rows for bar chart."""
        return self.query_all('''
            SELECT event_datetime::date AS day,
                   EXTRACT(EPOCH FROM MAX(event_datetime) - MIN(event_datetime)) / 3600 AS span_h
            FROM biostar_punch_logs
            WHERE biostar_user_id = %s
              AND EXTRACT(YEAR FROM event_datetime) = %s
              AND EXTRACT(MONTH FROM event_datetime) = %s
            GROUP BY event_datetime::date
            HAVING COUNT(*) >= 2
            ORDER BY day
        ''', (biostar_user_id, year, month))

    def get_missing_punch_days(self, user_id, biostar_user_id, sincron_employee_id,
                               sincron_company, year, month):
        """Return list of date strings for weekdays with no punch and no leave."""
        rows = self.query_all('''
            WITH month_days AS (
                SELECT generate_series(
                    make_date(%(y)s, %(m)s, 1),
                    (make_date(%(y)s, %(m)s, 1) + interval '1 month' - interval '1 day')::date,
                    '1 day'
                )::date AS d
            ),
            weekdays AS (
                SELECT d FROM month_days WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
            ),
            punch_days AS (
                SELECT DISTINCT event_datetime::date AS d
                FROM biostar_punch_logs
                WHERE biostar_user_id = %(bio_id)s
                  AND event_datetime >= make_date(%(y)s, %(m)s, 1)::timestamp
                  AND event_datetime < (make_date(%(y)s, %(m)s, 1) + interval '1 month')::timestamp
            ),
            sincron_leave AS (
                SELECT DISTINCT day AS d
                FROM sincron_timesheets
                WHERE sincron_employee_id = %(sin_id)s AND company_name = %(sin_co)s
                  AND year = %(y)s AND month = %(m)s
                  AND short_code IN ('CO','CM','CES','CIC','CMS','DLG')
            ),
            connecteam_leave AS (
                SELECT DISTINCT leave_date::date AS d
                FROM connecteam_form_submissions
                WHERE mapped_jarvis_user_id = %(uid)s
                  AND EXTRACT(YEAR FROM leave_date) = %(y)s
                  AND EXTRACT(MONTH FROM leave_date) = %(m)s
                  AND COALESCE(status, 'submitted') NOT IN ('rejected', 'cancelled')
            ),
            form_leave AS (
                SELECT DISTINCT (fs.answers->>'f_bi_leave_date')::date AS d
                FROM form_submissions fs
                JOIN forms f ON f.id = fs.form_id
                WHERE fs.respondent_user_id = %(uid)s
                  AND f.slug = 'bilet-de-invoire'
                  AND (fs.answers->>'f_bi_leave_date') IS NOT NULL
                  AND (fs.answers->>'f_bi_leave_date') ~ '^\d{4}-\d{2}-\d{2}$'
                  AND EXTRACT(YEAR FROM (fs.answers->>'f_bi_leave_date')::date) = %(y)s
                  AND EXTRACT(MONTH FROM (fs.answers->>'f_bi_leave_date')::date) = %(m)s
            ),
            holidays AS (
                SELECT date AS d FROM public_holidays
                WHERE year = %(y)s AND EXTRACT(MONTH FROM date) = %(m)s
            )
            SELECT wd.d::text AS missing_date
            FROM weekdays wd
            WHERE wd.d NOT IN (SELECT d FROM punch_days)
              AND wd.d NOT IN (SELECT d FROM sincron_leave)
              AND wd.d NOT IN (SELECT d FROM connecteam_leave)
              AND wd.d NOT IN (SELECT d FROM form_leave)
              AND wd.d NOT IN (SELECT d FROM holidays)
              AND wd.d <= CURRENT_DATE
            ORDER BY wd.d
        ''', {
            'uid': user_id, 'bio_id': biostar_user_id,
            'sin_id': sincron_employee_id, 'sin_co': sincron_company,
            'y': year, 'm': month,
        })
        return [r['missing_date'] for r in rows]

    def get_all_missing_punches_for_date(self, check_date):
        """Return all active BioStar-mapped employees with no punch and no leave on a date.

        Uses DISTINCT ON to avoid duplicate rows when an employee belongs to multiple structure nodes.
        """
        return self.query_all('''
            SELECT DISTINCT ON (be.mapped_jarvis_user_id)
                   be.mapped_jarvis_user_id AS user_id, u.name AS user_name,
                   u.company, be.biostar_user_id,
                   snm.node_id
            FROM biostar_employees be
            JOIN users u ON u.id = be.mapped_jarvis_user_id
            LEFT JOIN structure_node_members snm ON snm.user_id = u.id
            WHERE be.status = 'active'
              AND be.mapped_jarvis_user_id IS NOT NULL
              AND be.working_hours > 0
              AND be.schedule_start IS NOT NULL
              AND COALESCE(u.contract_status, 'active') = 'active'
              AND COALESCE(u.notify_missing_punch, TRUE) = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM biostar_punch_logs pl
                  WHERE pl.biostar_user_id = be.biostar_user_id
                    AND pl.event_datetime::date = %s
              )
              AND NOT EXISTS (
                  SELECT 1 FROM sincron_timesheets st
                  JOIN sincron_employees se ON se.sincron_employee_id = st.sincron_employee_id
                    AND se.company_name = st.company_name
                  WHERE se.mapped_jarvis_user_id = u.id
                    AND st.year = EXTRACT(YEAR FROM %s::date)
                    AND st.month = EXTRACT(MONTH FROM %s::date)
                    AND st.day = %s::date
                    AND st.short_code IN ('CO','CM','CES','CIC','CMS','DLG')
              )
              AND NOT EXISTS (
                  SELECT 1 FROM connecteam_form_submissions cfs
                  WHERE cfs.mapped_jarvis_user_id = u.id
                    AND cfs.leave_date::date = %s
                    AND COALESCE(cfs.status, 'submitted') NOT IN ('rejected', 'cancelled')
              )
              AND NOT EXISTS (
                  SELECT 1 FROM form_submissions fs
                  JOIN forms f ON f.id = fs.form_id
                  WHERE fs.respondent_user_id = u.id
                    AND f.slug = 'bilet-de-invoire'
                    AND (fs.answers->>'f_bi_leave_date') IS NOT NULL
                    AND (fs.answers->>'f_bi_leave_date') ~ '^\d{4}-\d{2}-\d{2}$'
                    AND (fs.answers->>'f_bi_leave_date')::date = %s
              )
              AND NOT EXISTS (
                  SELECT 1 FROM public_holidays ph WHERE ph.date = %s
              )
            ORDER BY be.mapped_jarvis_user_id
        ''', (check_date, check_date, check_date, check_date, check_date, check_date, check_date))

    def get_daily_sincron_codes(self, sincron_employee_id, company_name, year, month):
        """Return list of {day, short_code, unit, value} rows for timeline."""
        return self.query_all('''
            SELECT day, short_code, unit, value
            FROM sincron_timesheets
            WHERE sincron_employee_id = %s AND company_name = %s
              AND year = %s AND month = %s
              AND short_code != 'ZLS'
            ORDER BY day, short_code
        ''', (sincron_employee_id, company_name, year, month))
