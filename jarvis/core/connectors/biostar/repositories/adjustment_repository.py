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
            WITH daily AS (
                SELECT
                    pl.biostar_user_id,
                    be.name,
                    be.email,
                    be.user_group_name,
                    be.schedule_start,
                    be.schedule_end,
                    be.lunch_break_minutes,
                    be.working_hours,
                    be.mapped_jarvis_user_id,
                    u.name AS mapped_jarvis_user_name,
                    MIN(pl.event_datetime) AS first_punch,
                    MAX(pl.event_datetime) AS last_punch,
                    COUNT(*) AS total_punches,
                    EXTRACT(EPOCH FROM (MAX(pl.event_datetime) - MIN(pl.event_datetime))) AS duration_seconds
                FROM biostar_punch_logs pl
                LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
                LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
                WHERE pl.event_datetime::date = %s::date
                  AND be.status = 'active'
                GROUP BY pl.biostar_user_id, be.name, be.email, be.user_group_name,
                         be.schedule_start, be.schedule_end, be.lunch_break_minutes,
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
        ''', (date_str, date_str,
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
        """Insert or update a daily adjustment."""
        return self.execute('''
            INSERT INTO biostar_daily_adjustments
                (biostar_user_id, date, original_first_punch, original_last_punch,
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
        """Remove an adjustment (revert to original)."""
        return self.execute('''
            DELETE FROM biostar_daily_adjustments
            WHERE biostar_user_id = %s AND date = %s::date
        ''', (biostar_user_id, date_str))

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
