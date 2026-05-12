"""Repository for biostar_daily_adjustments."""

from core.base_repository import BaseRepository


class AdjustmentRepository(BaseRepository):
    """Data access for biostar_daily_adjustments."""

    def get_off_schedule(self, date_str, threshold_minutes=15):
        """Get employees with any schedule deviation exceeding threshold.

        Compliance criteria:
        - Missing checkout : only 1 punch + past day (forgot to check out)
        - Overtime          : net worked > working_hours + threshold
        - Late arrival      : first punch > schedule_start + threshold
        - Early departure   : last punch < schedule_end − threshold
        - Under-hours       : net worked < working_hours − threshold (multi-punch)
        - Single punch on today → NEVER show (no checkout yet, wait for next sync)
        - Excludes employees already adjusted for that date
        """
        return self.query_all('''
            WITH sincron_day AS (
                SELECT DISTINCT ON (se.mapped_jarvis_user_id)
                       se.mapped_jarvis_user_id,
                       st.program_in AS program_start,
                       st.program_out AS program_end,
                       st.program_break AS program_lunch
                FROM sincron_employees se
                JOIN sincron_timesheets st
                  ON st.sincron_employee_id = se.sincron_employee_id
                  AND st.company_name = se.company_name
                  AND st.day = %s::date
                  AND st.short_code IN ('OZ', 'OS')
                  AND st.program_in IS NOT NULL
                  AND st.program_out IS NOT NULL
                WHERE se.is_active = TRUE
                  AND se.mapped_jarvis_user_id IS NOT NULL
                ORDER BY se.mapped_jarvis_user_id, se.norma_lucru DESC NULLS LAST
            ),
            deduped AS (
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime
                FROM biostar_punch_logs pl
                LEFT JOIN biostar_employees be2 ON be2.biostar_user_id = pl.biostar_user_id
                WHERE pl.event_datetime::date = %s::date
                  AND be2.status = 'active'
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            daily AS (
                SELECT
                    d.biostar_user_id,
                    be.name,
                    be.email,
                    be.user_group_name,
                    COALESCE(sd.program_start, be.schedule_start) AS schedule_start,
                    COALESCE(sd.program_end, be.schedule_end) AS schedule_end,
                    COALESCE(sd.program_lunch, be.lunch_break_minutes) AS lunch_break_minutes,
                    be.working_hours,
                    be.mapped_jarvis_user_id,
                    u.name AS mapped_jarvis_user_name,
                    MIN(d.event_datetime) AS first_punch,
                    MAX(d.event_datetime) AS last_punch,
                    COUNT(*) AS total_punches,
                    EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                LEFT JOIN biostar_employees be ON be.biostar_user_id = d.biostar_user_id
                LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
                LEFT JOIN sincron_day sd ON sd.mapped_jarvis_user_id = be.mapped_jarvis_user_id
                GROUP BY d.biostar_user_id, be.name, be.email, be.user_group_name,
                         COALESCE(sd.program_start, be.schedule_start),
                         COALESCE(sd.program_end, be.schedule_end),
                         COALESCE(sd.program_lunch, be.lunch_break_minutes),
                         be.working_hours, be.mapped_jarvis_user_id, u.name
            ),
            flagged AS (
                SELECT d.*,
                       EXTRACT(EPOCH FROM (d.first_punch::time - d.schedule_start)) / 60 AS deviation_in,
                       CASE WHEN d.total_punches > 1
                            THEN EXTRACT(EPOCH FROM (d.last_punch::time - d.schedule_end)) / 60
                            ELSE NULL END AS deviation_out,
                       CASE WHEN d.total_punches > 1
                            THEN ROUND((d.duration_seconds / 60.0 - d.lunch_break_minutes) - d.working_hours * 60)
                            ELSE NULL END AS overtime_minutes,
                       d.total_punches = 1 AND %s::date < CURRENT_DATE AS missing_checkout
                FROM daily d
            )
            SELECT f.*,
                   -- Compute violation type(s) as a comma-separated string
                   ARRAY_TO_STRING(ARRAY_REMOVE(ARRAY[
                       CASE WHEN f.missing_checkout THEN 'missing_checkout' END,
                       CASE WHEN NOT f.missing_checkout AND f.total_punches > 1
                            AND f.deviation_in > %s THEN 'late_arrival' END,
                       CASE WHEN NOT f.missing_checkout AND f.total_punches > 1
                            AND f.deviation_out < -%s THEN 'early_departure' END,
                       CASE WHEN NOT f.missing_checkout AND f.total_punches > 1
                            AND f.overtime_minutes > %s THEN 'overtime' END,
                       CASE WHEN NOT f.missing_checkout AND f.total_punches > 1
                            AND (f.duration_seconds / 60.0 - f.lunch_break_minutes) < (f.working_hours * 60 - %s)
                            THEN 'under_hours' END
                   ], NULL), ',') AS violation_types,
                   adj.id AS adjustment_id,
                   adj.adjusted_first_punch,
                   adj.adjusted_last_punch,
                   adj.adjustment_type,
                   adj.adjusted_by,
                   adj.notes
            FROM flagged f
            LEFT JOIN biostar_daily_adjustments adj
                ON adj.biostar_user_id = f.biostar_user_id AND adj.date = %s::date
            WHERE adj.id IS NULL
              AND (
                  -- Case 1: only 1 punch + past day = forgot to check out
                  f.missing_checkout
                  -- Case 2: overtime
                  OR (f.total_punches > 1
                      AND f.overtime_minutes > %s)
                  -- Case 3: late arrival
                  OR (f.total_punches > 1
                      AND f.deviation_in > %s)
                  -- Case 4: early departure
                  OR (f.total_punches > 1
                      AND f.deviation_out < -%s)
                  -- Case 5: under-hours
                  OR (f.total_punches > 1
                      AND (f.duration_seconds / 60.0 - f.lunch_break_minutes) < (f.working_hours * 60 - %s))
              )
            ORDER BY f.name
        ''', (date_str, date_str, date_str,
              threshold_minutes, threshold_minutes, threshold_minutes, threshold_minutes,
              date_str,
              threshold_minutes, threshold_minutes, threshold_minutes, threshold_minutes))

    def get_adjustments(self, date_str):
        """Get all adjustments for a given date."""
        return self.query_all('''
            SELECT adj.*,
                   be.name,
                   be.email,
                   be.user_group_name,
                   u.name AS adjusted_by_name
            FROM biostar_daily_adjustments adj
            LEFT JOIN biostar_employees be ON be.biostar_user_id = adj.biostar_user_id
            LEFT JOIN users u ON u.id = adj.adjusted_by
            WHERE adj.date = %s::date
            ORDER BY be.name
        ''', (date_str,))

    def upsert_adjustment(self, data):
        """Insert or update a daily adjustment.

        One adjustment per (biostar_user_id, date).  For multi-contract employees
        each group's buid gets its own row.
        """
        return self.execute('''
            INSERT INTO biostar_daily_adjustments
                (biostar_user_id, date,
                 original_first_punch, original_last_punch,
                 original_duration_seconds, adjusted_first_punch, adjusted_last_punch,
                 adjusted_duration_seconds, schedule_start, schedule_end,
                 lunch_break_minutes, working_hours,
                 deviation_minutes_in, deviation_minutes_out,
                 adjustment_type, adjusted_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (biostar_user_id, date) DO UPDATE SET
                adjusted_first_punch = EXCLUDED.adjusted_first_punch,
                adjusted_last_punch = EXCLUDED.adjusted_last_punch,
                adjusted_duration_seconds = EXCLUDED.adjusted_duration_seconds,
                adjustment_type = EXCLUDED.adjustment_type,
                adjusted_by = EXCLUDED.adjusted_by,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING id
        ''', (
            data['biostar_user_id'], data['date'],
            data['original_first_punch'], data['original_last_punch'],
            data.get('original_duration_seconds'),
            data['adjusted_first_punch'], data['adjusted_last_punch'],
            data.get('adjusted_duration_seconds'),
            data.get('schedule_start'), data.get('schedule_end'),
            data.get('lunch_break_minutes'), data.get('working_hours'),
            data.get('deviation_minutes_in'), data.get('deviation_minutes_out'),
            data.get('adjustment_type', 'manual'),
            data.get('adjusted_by'),
            data.get('notes'),
        ), returning=True)

    def delete_adjustment(self, biostar_user_id, date_str):
        """Remove the adjustment for a specific buid + date."""
        return self.execute('''
            DELETE FROM biostar_daily_adjustments
            WHERE biostar_user_id = %s AND date = %s::date
        ''', (biostar_user_id, date_str))

    def delete_adjustments_range(self, start_date, end_date, adjustment_type=None):
        """Delete all adjustments in a date range. Optionally filter by type."""
        if adjustment_type:
            return self.execute('''
                DELETE FROM biostar_daily_adjustments
                WHERE date BETWEEN %s::date AND %s::date
                  AND adjustment_type = %s
            ''', (start_date, end_date, adjustment_type))
        return self.execute('''
            DELETE FROM biostar_daily_adjustments
            WHERE date BETWEEN %s::date AND %s::date
        ''', (start_date, end_date))

    def get_employee_history(self, biostar_user_id, start_date=None, end_date=None):
        """Get adjustment history for one employee (audit trail)."""
        conditions = ['adj.biostar_user_id = %s']
        params = [biostar_user_id]
        if start_date:
            conditions.append('adj.date >= %s::date')
            params.append(start_date)
        if end_date:
            conditions.append('adj.date <= %s::date')
            params.append(end_date)
        where = ' AND '.join(conditions)
        return self.query_all(f'''
            SELECT adj.*,
                   be.name,
                   be.user_group_name,
                   u.name AS adjusted_by_name
            FROM biostar_daily_adjustments adj
            LEFT JOIN biostar_employees be ON be.biostar_user_id = adj.biostar_user_id
            LEFT JOIN users u ON u.id = adj.adjusted_by
            WHERE {where}
            ORDER BY adj.date DESC
        ''', params)

    def get_absent_employees(self, date_str):
        """Get active employees with schedules who have NO punches for the date.

        Excludes:
        - Employees already adjusted for that date (combined adjustment only;
          per-company adjustments are handled in auto_adjust_all)
        - Current day (absent might still arrive)

        NOTE: Sincron leave filtering is now done in Python (auto_adjust_all)
        to support per-company leave for multi-contract employees.
        """
        return self.query_all('''
            WITH sincron_day AS (
                SELECT DISTINCT ON (se.mapped_jarvis_user_id)
                       se.mapped_jarvis_user_id,
                       st.program_in  AS program_start,
                       st.program_out AS program_end,
                       st.program_break AS program_lunch
                FROM sincron_employees se
                JOIN sincron_timesheets st
                  ON st.sincron_employee_id = se.sincron_employee_id
                  AND st.company_name = se.company_name
                  AND st.day = %s::date
                  AND st.short_code IN ('OZ','OS')
                  AND st.program_in IS NOT NULL
                  AND st.program_out IS NOT NULL
                WHERE se.is_active = TRUE
                  AND se.mapped_jarvis_user_id IS NOT NULL
                ORDER BY se.mapped_jarvis_user_id, se.norma_lucru DESC NULLS LAST
            ),
            has_punches AS (
                SELECT DISTINCT pl.biostar_user_id
                FROM biostar_punch_logs pl
                WHERE pl.event_datetime::date = %s::date
            )
            SELECT
                be.biostar_user_id,
                be.name,
                be.email,
                be.user_group_name,
                COALESCE(sd.program_start, be.schedule_start) AS schedule_start,
                COALESCE(sd.program_end,   be.schedule_end)   AS schedule_end,
                COALESCE(sd.program_lunch,  be.lunch_break_minutes) AS lunch_break_minutes,
                be.working_hours,
                be.mapped_jarvis_user_id
            FROM biostar_employees be
            LEFT JOIN sincron_day sd
              ON sd.mapped_jarvis_user_id = be.mapped_jarvis_user_id
            LEFT JOIN has_punches hp
              ON hp.biostar_user_id = be.biostar_user_id
            LEFT JOIN biostar_daily_adjustments adj
              ON adj.biostar_user_id = be.biostar_user_id AND adj.date = %s::date
            WHERE be.status = 'active'
              AND COALESCE(sd.program_start, be.schedule_start) IS NOT NULL
              AND COALESCE(sd.program_end,   be.schedule_end)   IS NOT NULL
              AND hp.biostar_user_id IS NULL
              AND adj.id IS NULL
              AND %s::date < CURRENT_DATE
            ORDER BY be.name
        ''', (date_str, date_str, date_str, date_str))

    def get_unadjusted_dates(self):
        """Get all distinct past dates with punch logs that have unadjusted employees."""
        return self.query_all('''
            SELECT DISTINCT pl.event_datetime::date AS punch_date
            FROM biostar_punch_logs pl
            LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            WHERE pl.event_datetime::date < CURRENT_DATE
              AND be.status = 'active'
            ORDER BY punch_date DESC
        ''')

    def get_adjustment_count(self, date_str):
        """Count adjustments for a date."""
        row = self.query_one(
            'SELECT COUNT(*) AS cnt FROM biostar_daily_adjustments WHERE date = %s::date',
            (date_str,)
        )
        return row['cnt'] if row else 0
