"""BioStar data repository — employees and punch logs."""

import json
from core.base_repository import BaseRepository


class BioStarRepository(BaseRepository):
    """Data access for biostar_employees and biostar_punch_logs."""

    # ── Employees ──

    def get_all_employees(self, active_only=True):
        """Get all BioStar employees with their JARVIS mapping."""
        sql = '''
            SELECT be.*,
                   u.name AS mapped_jarvis_user_name,
                   COALESCE(co.company, u.company) AS jarvis_company,
                   u.is_active AS jarvis_user_active
            FROM biostar_employees be
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
            LEFT JOIN companies co ON co.id = u.company_id
        '''
        if active_only:
            sql += """ WHERE be.status = 'active'
              AND (be.user_group_name IS NULL OR (be.user_group_name NOT ILIKE '%%plecati%%' AND be.user_group_name NOT ILIKE '%%contracte inchise%%'))
              AND (be.mapped_jarvis_user_id IS NULL OR COALESCE((SELECT contract_status FROM users WHERE id = be.mapped_jarvis_user_id), 'active') != 'closed')"""
        sql += ' ORDER BY be.name'
        return self.query_all(sql)

    def get_employee_by_biostar_id(self, biostar_user_id):
        """Get a single employee by BioStar user ID."""
        return self.query_one(
            'SELECT * FROM biostar_employees WHERE biostar_user_id = %s',
            (biostar_user_id,)
        )

    def upsert_employee(self, data):
        """Insert a new BioStar employee, skip if exists. Returns the row."""
        return self.execute('''
            INSERT INTO biostar_employees
                (biostar_user_id, name, email, phone, user_group_id,
                 user_group_name, card_ids, status, last_synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (biostar_user_id) DO UPDATE SET
                last_synced_at = NOW()
            RETURNING id, biostar_user_id
        ''', (
            data['biostar_user_id'], data['name'], data.get('email'),
            data.get('phone'), data.get('user_group_id'),
            data.get('user_group_name'), json.dumps(data.get('card_ids', [])),
            data.get('status', 'active')
        ), returning=True)

    def bulk_upsert_employees(self, employees):
        """Insert new employees, skip existing. Returns {created, updated, skipped}."""
        def _work(cursor):
            created = 0
            skipped = 0
            for emp in employees:
                cursor.execute('''
                    INSERT INTO biostar_employees
                        (biostar_user_id, name, email, phone, user_group_id,
                         user_group_name, card_ids, status, last_synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (biostar_user_id) DO UPDATE SET
                        last_synced_at = NOW()
                ''', (
                    emp['biostar_user_id'], emp['name'], emp.get('email'),
                    emp.get('phone'), emp.get('user_group_id'),
                    emp.get('user_group_name'), json.dumps(emp.get('card_ids', [])),
                    emp.get('status', 'active')
                ))
                if cursor.rowcount > 0:
                    created += 1
                else:
                    skipped += 1
            return {'created': created, 'updated': 0, 'skipped': skipped}
        return self.execute_many(_work)

    def update_mapping(self, biostar_user_id, jarvis_user_id, method='manual', confidence=100.0):
        """Map a BioStar employee to a JARVIS user."""
        return self.execute('''
            UPDATE biostar_employees
            SET mapped_jarvis_user_id = %s, mapping_method = %s,
                mapping_confidence = %s, updated_at = NOW()
            WHERE biostar_user_id = %s
        ''', (jarvis_user_id, method, confidence, biostar_user_id))

    def update_schedule(self, biostar_user_id, lunch_break_minutes, working_hours,
                        schedule_start=None, schedule_end=None):
        """Update lunch break, working hours, and office hours for an employee."""
        return self.execute('''
            UPDATE biostar_employees
            SET lunch_break_minutes = %s, working_hours = %s,
                schedule_start = COALESCE(%s, schedule_start),
                schedule_end = COALESCE(%s, schedule_end),
                updated_at = NOW()
            WHERE biostar_user_id = %s
        ''', (lunch_break_minutes, working_hours, schedule_start, schedule_end, biostar_user_id))

    def bulk_update_schedule(self, biostar_user_ids, lunch_break_minutes=None,
                             working_hours=None, schedule_start=None, schedule_end=None):
        """Bulk update schedule fields for multiple employees. Only non-None fields are updated."""
        if not biostar_user_ids:
            return 0
        sets = []
        params = []
        if lunch_break_minutes is not None:
            sets.append('lunch_break_minutes = %s')
            params.append(lunch_break_minutes)
        if working_hours is not None:
            sets.append('working_hours = %s')
            params.append(working_hours)
        if schedule_start is not None:
            sets.append('schedule_start = %s')
            params.append(schedule_start)
        if schedule_end is not None:
            sets.append('schedule_end = %s')
            params.append(schedule_end)
        if not sets:
            return 0
        sets.append('updated_at = NOW()')
        placeholders = ','.join(['%s'] * len(biostar_user_ids))
        params.extend(biostar_user_ids)
        sql = f"UPDATE biostar_employees SET {', '.join(sets)} WHERE biostar_user_id IN ({placeholders})"
        self.execute(sql, params)
        return len(biostar_user_ids)

    def toggle_blacklist(self, biostar_user_id):
        """Toggle blacklist status for a single employee. Returns new status."""
        return self.execute('''
            UPDATE biostar_employees
            SET is_blacklisted = NOT is_blacklisted, updated_at = NOW()
            WHERE biostar_user_id = %s
            RETURNING is_blacklisted
        ''', (biostar_user_id,), returning=True)

    def blacklist_group(self, group_name, blacklisted=True):
        """Set blacklist status for all employees in a group."""
        return self.execute('''
            UPDATE biostar_employees
            SET is_blacklisted = %s, updated_at = NOW()
            WHERE user_group_name = %s
        ''', (blacklisted, group_name))

    def bulk_blacklist(self, biostar_user_ids, blacklisted=True):
        """Set blacklist status for multiple employees."""
        if not biostar_user_ids:
            return 0
        placeholders = ','.join(['%s'] * len(biostar_user_ids))
        self.execute(
            f"UPDATE biostar_employees SET is_blacklisted = %s, updated_at = NOW() WHERE biostar_user_id IN ({placeholders})",
            [blacklisted] + list(biostar_user_ids)
        )
        return len(biostar_user_ids)

    def bulk_deactivate(self, biostar_user_ids):
        """Soft-delete employees by setting status to inactive."""
        if not biostar_user_ids:
            return 0
        placeholders = ','.join(['%s'] * len(biostar_user_ids))
        self.execute(
            f"UPDATE biostar_employees SET status = 'inactive', updated_at = NOW() WHERE biostar_user_id IN ({placeholders})",
            biostar_user_ids
        )
        return len(biostar_user_ids)

    def remove_mapping(self, biostar_user_id):
        """Remove JARVIS user mapping."""
        return self.execute('''
            UPDATE biostar_employees
            SET mapped_jarvis_user_id = NULL, mapping_method = NULL,
                mapping_confidence = NULL, updated_at = NOW()
            WHERE biostar_user_id = %s
        ''', (biostar_user_id,))

    def get_unmapped_employees(self):
        """Get employees without JARVIS user mapping."""
        return self.query_all('''
            SELECT * FROM biostar_employees
            WHERE mapped_jarvis_user_id IS NULL AND status = 'active'
            ORDER BY name
        ''')

    def get_employee_stats(self):
        """Get employee counts."""
        return self.query_one('''
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'active') AS active,
                COUNT(*) FILTER (WHERE mapped_jarvis_user_id IS NOT NULL) AS mapped,
                COUNT(*) FILTER (WHERE mapped_jarvis_user_id IS NULL AND status = 'active') AS unmapped
            FROM biostar_employees
        ''')

    # ── Auto-mapping (SQL-based, mirrors Sincron style) ──

    def auto_map_by_cnp(self):
        """Link unmapped BioStar employees to JARVIS users via Sincron CNP.

        BioStar doesn't provide CNP directly. Instead, match BioStar employees
        to users who have CNP (populated from Sincron) by cross-referencing
        name or email.
        CNP is canonical in users table only — no longer stored in biostar_employees.
        """
        # BioStar has no CNP column; this is now a no-op placeholder.
        # Real CNP matching flows through Sincron → users.cnp → auto_map_cross_verified.
        return 0

    def auto_map_by_email(self):
        """Link unmapped BioStar employees to JARVIS users by email (confidence 100)."""
        return self.execute('''
            UPDATE biostar_employees be
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'auto_email',
                mapping_confidence = 100,
                updated_at = NOW()
            FROM users u
            WHERE be.mapped_jarvis_user_id IS NULL
              AND be.status = 'active'
              AND be.email IS NOT NULL
              AND be.email <> ''
              AND u.email IS NOT NULL
              AND u.email <> ''
              AND COALESCE(u.contract_status, 'active') != 'closed'
              AND LOWER(TRIM(be.email)) = LOWER(TRIM(u.email))
        ''')

    def auto_map_by_name(self):
        """Link unmapped BioStar employees to JARVIS users by exact name (confidence 90)."""
        return self.execute('''
            UPDATE biostar_employees be
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'auto_name',
                mapping_confidence = 90,
                updated_at = NOW()
            FROM users u
            WHERE be.mapped_jarvis_user_id IS NULL
              AND be.status = 'active'
              AND be.name IS NOT NULL
              AND be.name <> ''
              AND u.name IS NOT NULL
              AND u.name <> ''
              AND COALESCE(u.contract_status, 'active') != 'closed'
              AND LOWER(TRIM(be.name)) = LOWER(TRIM(u.name))
        ''')

    def auto_map_cross_verified(self):
        """Link unmapped BioStar employees via existing Sincron mappings (confidence 95).

        For each still-unmapped BioStar row, if a sincron_employees row is already
        mapped to a JARVIS user AND any of {email, full-name, reversed full-name}
        match, copy the same mapped_jarvis_user_id across with
        method='cross_verified'.
        """
        return self.execute('''
            UPDATE biostar_employees be
            SET mapped_jarvis_user_id = se.mapped_jarvis_user_id,
                mapping_method = 'cross_verified',
                mapping_confidence = 95,
                updated_at = NOW()
            FROM sincron_employees se
            JOIN users u ON u.id = se.mapped_jarvis_user_id
            WHERE be.mapped_jarvis_user_id IS NULL
              AND be.status = 'active'
              AND se.mapped_jarvis_user_id IS NOT NULL
              AND se.is_active = TRUE
              AND COALESCE(u.contract_status, 'active') != 'closed'
              AND (
                    (be.email IS NOT NULL AND be.email <> ''
                     AND u.email IS NOT NULL AND u.email <> ''
                     AND LOWER(TRIM(be.email)) = LOWER(TRIM(u.email)))
                 OR (be.name IS NOT NULL AND be.name <> ''
                     AND u.name IS NOT NULL AND u.name <> ''
                     AND LOWER(TRIM(be.name)) = LOWER(TRIM(u.name)))
                 OR (be.name IS NOT NULL AND be.name <> ''
                     AND se.nume IS NOT NULL AND se.prenume IS NOT NULL
                     AND LOWER(TRIM(be.name)) =
                         LOWER(TRIM(se.nume || ' ' || se.prenume)))
                 OR (be.name IS NOT NULL AND be.name <> ''
                     AND se.nume IS NOT NULL AND se.prenume IS NOT NULL
                     AND LOWER(TRIM(be.name)) =
                         LOWER(TRIM(se.prenume || ' ' || se.nume)))
              )
        ''')

    # ── Punch Logs ──

    def insert_punch_logs(self, logs):
        """Bulk insert punch logs with ON CONFLICT DO NOTHING for dedup."""
        def _work(cursor):
            inserted = 0
            skipped = 0
            for log in logs:
                cursor.execute('''
                    INSERT INTO biostar_punch_logs
                        (biostar_event_id, biostar_user_id, event_datetime,
                         event_type, direction, device_id, device_name,
                         door_id, door_name, auth_type, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (biostar_event_id, (event_datetime::date)) DO NOTHING
                ''', (
                    log['biostar_event_id'], log['biostar_user_id'],
                    log['event_datetime'], log['event_type'],
                    log.get('direction'), log.get('device_id'),
                    log.get('device_name'), log.get('door_id'),
                    log.get('door_name'), log.get('auth_type'),
                    json.dumps(log.get('raw_data', {}))
                ))
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            return {'inserted': inserted, 'skipped': skipped}
        return self.execute_many(_work)

    def get_punch_logs(self, biostar_user_id=None, start_date=None,
                       end_date=None, limit=100, offset=0):
        """Get punch logs with optional filters."""
        conditions = []
        params = []

        if biostar_user_id:
            conditions.append('pl.biostar_user_id = %s')
            params.append(biostar_user_id)
        if start_date:
            conditions.append('pl.event_datetime >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('pl.event_datetime <= %s')
            params.append(end_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        params.extend([limit, offset])

        return self.query_all(f'''
            SELECT pl.*, be.name AS employee_name
            FROM biostar_punch_logs pl
            LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            {where}
            ORDER BY pl.event_datetime DESC
            LIMIT %s OFFSET %s
        ''', params)

    def get_punch_log_count(self, biostar_user_id=None, start_date=None, end_date=None):
        """Count punch logs with optional filters."""
        conditions = []
        params = []

        if biostar_user_id:
            conditions.append('biostar_user_id = %s')
            params.append(biostar_user_id)
        if start_date:
            conditions.append('event_datetime >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('event_datetime <= %s')
            params.append(end_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        row = self.query_one(f'SELECT COUNT(*) AS cnt FROM biostar_punch_logs {where}', params)
        return row['cnt'] if row else 0

    def get_last_event_datetime(self):
        """Get the latest event_datetime for incremental sync cursor."""
        row = self.query_one('SELECT MAX(event_datetime) AS last_dt FROM biostar_punch_logs')
        return row['last_dt'] if row else None

    def get_daily_summary(self, date_str, jarvis_user_ids=None):
        """Get per-employee daily punch summary with group, duration, mapped user, schedule.

        Also returns adjusted punch times from biostar_daily_adjustments if they exist.
        """
        params = [date_str]
        extra_where = ''
        if jarvis_user_ids:
            extra_where = ' AND be2.mapped_jarvis_user_id = ANY(%s)'
            params.append(jarvis_user_ids)
        # date_str used for the adjustment JOIN and UNION
        params.append(date_str)
        params.append(date_str)
        return self.query_all(f'''
            WITH deduped AS (
                -- Collapse same-minute punches from the same user (BioStar zone
                -- terminals register one badge across multiple devices simultaneously)
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime
                FROM biostar_punch_logs pl
                LEFT JOIN biostar_employees be2 ON be2.biostar_user_id = pl.biostar_user_id
                WHERE pl.event_datetime::date = %s::date
                  AND (be2.is_blacklisted IS NULL OR be2.is_blacklisted = FALSE){extra_where}
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            punches AS (
                SELECT
                    d.biostar_user_id,
                    be.name,
                    be.email,
                    be.user_group_name,
                    be.mapped_jarvis_user_id,
                    u.name AS mapped_jarvis_user_name,
                    COALESCE(co.company, u.company) AS jarvis_company,
                    u.department AS jarvis_department,
                    be.lunch_break_minutes,
                    be.working_hours,
                    be.schedule_start,
                    be.schedule_end,
                    u.is_active AS jarvis_user_active,
                    MIN(d.event_datetime) AS first_punch,
                    MAX(d.event_datetime) AS last_punch,
                    COUNT(*) AS total_punches,
                    EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                LEFT JOIN biostar_employees be ON be.biostar_user_id = d.biostar_user_id
                LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
                LEFT JOIN companies co ON co.id = u.company_id
                GROUP BY d.biostar_user_id, be.name, be.email, be.user_group_name,
                         be.mapped_jarvis_user_id, u.name, co.company, u.company, u.department,
                         be.lunch_break_minutes, be.working_hours,
                         be.schedule_start, be.schedule_end, u.is_active
            )
            SELECT p.*,
                   adj.adjusted_first_punch,
                   adj.adjusted_last_punch,
                   adj.adjustment_type
            FROM punches p
            LEFT JOIN biostar_daily_adjustments adj
                ON adj.biostar_user_id = p.biostar_user_id AND adj.date = %s::date
            -- Exclude dismissed/closed JARVIS users and departed BioStar groups
            WHERE (p.mapped_jarvis_user_id IS NULL OR p.jarvis_user_active = TRUE)
              AND (p.user_group_name IS NULL OR (p.user_group_name NOT ILIKE '%%plecati%%' AND p.user_group_name NOT ILIKE '%%contracte inchise%%'))

            UNION ALL

            -- Include absent employees who have adjustments but no punches
            SELECT
                adj2.biostar_user_id,
                be3.name,
                be3.email,
                be3.user_group_name,
                be3.mapped_jarvis_user_id,
                u3.name AS mapped_jarvis_user_name,
                COALESCE(co3.company, u3.company) AS jarvis_company,
                u3.department AS jarvis_department,
                be3.lunch_break_minutes,
                be3.working_hours,
                be3.schedule_start,
                be3.schedule_end,
                u3.is_active AS jarvis_user_active,
                NULL::timestamptz AS first_punch,
                NULL::timestamptz AS last_punch,
                0 AS total_punches,
                0 AS duration_seconds,
                adj2.adjusted_first_punch,
                adj2.adjusted_last_punch,
                adj2.adjustment_type
            FROM biostar_daily_adjustments adj2
            JOIN biostar_employees be3 ON be3.biostar_user_id = adj2.biostar_user_id
            LEFT JOIN users u3 ON u3.id = be3.mapped_jarvis_user_id
            LEFT JOIN companies co3 ON co3.id = u3.company_id
            WHERE adj2.date = %s::date
              AND adj2.original_first_punch IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM punches p2 WHERE p2.biostar_user_id = adj2.biostar_user_id
              )
              -- Exclude dismissed/closed JARVIS users and departed BioStar groups
              AND (be3.mapped_jarvis_user_id IS NULL OR u3.is_active = TRUE)
              AND (be3.user_group_name IS NULL OR (be3.user_group_name NOT ILIKE '%%plecati%%' AND be3.user_group_name NOT ILIKE '%%contracte inchise%%'))

            ORDER BY jarvis_company NULLS LAST, name
        ''', params)

    def get_range_summary(self, start_date, end_date, jarvis_user_ids=None):
        """Get per-employee aggregated punch summary over a date range."""
        params = [start_date, end_date]
        extra_where = ''
        if jarvis_user_ids:
            extra_where = ' AND be.mapped_jarvis_user_id = ANY(%s)'
            params.append(jarvis_user_ids)
        return self.query_all(f'''
            WITH deduped AS (
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime
                FROM biostar_punch_logs pl
                LEFT JOIN biostar_employees be2 ON be2.biostar_user_id = pl.biostar_user_id
                WHERE pl.event_datetime::date BETWEEN %s::date AND %s::date
                  AND (be2.is_blacklisted IS NULL OR be2.is_blacklisted = FALSE)
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            daily AS (
                SELECT
                    d.biostar_user_id,
                    d.event_datetime::date AS day,
                    MIN(d.event_datetime) AS first_punch,
                    MAX(d.event_datetime) AS last_punch,
                    COUNT(*) AS punches,
                    EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                GROUP BY d.biostar_user_id, d.event_datetime::date
            )
            SELECT
                d.biostar_user_id,
                be.name,
                be.email,
                be.user_group_name,
                be.mapped_jarvis_user_id,
                u.name AS mapped_jarvis_user_name,
                COALESCE(co.company, u.company) AS jarvis_company,
                u.department AS jarvis_department,
                be.lunch_break_minutes,
                be.working_hours,
                be.schedule_start,
                be.schedule_end,
                COUNT(d.day) AS days_present,
                COUNT(CASE WHEN d.punches = 1 THEN 1 END) AS single_punch_days,
                SUM(d.duration_seconds) AS total_duration_seconds,
                AVG(d.duration_seconds) AS avg_duration_seconds,
                SUM(d.punches) AS total_punches,
                MIN(d.first_punch) AS earliest_punch,
                MAX(d.last_punch) AS latest_punch,
                AVG(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.first_punch::time) END) AS avg_check_in_epoch,
                AVG(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.last_punch::time) END) AS avg_check_out_epoch,
                STDDEV(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.first_punch::time) END) AS stddev_check_in_epoch,
                STDDEV(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.last_punch::time) END) AS stddev_check_out_epoch,
                SUM(COALESCE(adj.adjusted_duration_seconds, d.duration_seconds)) AS adjusted_total_duration_seconds,
                COUNT(adj.id) AS adjustment_count
            FROM daily d
            LEFT JOIN biostar_employees be ON be.biostar_user_id = d.biostar_user_id
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
            LEFT JOIN companies co ON co.id = u.company_id
            LEFT JOIN biostar_daily_adjustments adj
                ON adj.biostar_user_id = d.biostar_user_id AND adj.date = d.day
            WHERE (be.mapped_jarvis_user_id IS NULL OR (u.is_active = TRUE AND COALESCE(u.contract_status, 'active') != 'closed'))
              AND (be.user_group_name IS NULL OR (be.user_group_name NOT ILIKE '%%plecati%%' AND be.user_group_name NOT ILIKE '%%contracte inchise%%')){extra_where}
            GROUP BY d.biostar_user_id, be.name, be.email, be.user_group_name,
                     be.mapped_jarvis_user_id, u.name, co.company, u.company, u.department,
                     be.lunch_break_minutes, be.working_hours,
                     be.schedule_start, be.schedule_end
            ORDER BY COALESCE(co.company, u.company) NULLS LAST, be.name
        ''', params)

    def get_employee_punches(self, biostar_user_id, date_str):
        """Get all punch events for one employee on a specific date."""
        return self.query_all('''
            SELECT pl.*, be.name AS employee_name, be.user_group_name
            FROM biostar_punch_logs pl
            LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            WHERE pl.biostar_user_id = %s AND pl.event_datetime::date = %s::date
            ORDER BY pl.event_datetime ASC
        ''', (biostar_user_id, date_str))

    def get_employee_daily_history(self, biostar_user_id, start_date, end_date):
        """Get per-day punch summary for one employee over a date range.

        Also returns adjusted punch times from biostar_daily_adjustments if they exist.
        Uses Sincron per-day schedule when available (COALESCE over BioStar static).
        """
        return self.query_all('''
            WITH deduped AS (
                SELECT DISTINCT ON (date_trunc('minute', pl.event_datetime))
                    pl.event_datetime
                FROM biostar_punch_logs pl
                WHERE pl.biostar_user_id = %s
                  AND pl.event_datetime::date BETWEEN %s::date AND %s::date
                ORDER BY date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            daily AS (
                SELECT
                    d.event_datetime::date AS date,
                    MIN(d.event_datetime) AS first_punch,
                    MAX(d.event_datetime) AS last_punch,
                    COUNT(*) AS total_punches,
                    EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds,
                    COALESCE(be.lunch_break_minutes) AS lunch_break_minutes,
                    be.working_hours,
                    be.schedule_start AS static_schedule_start,
                    be.schedule_end AS static_schedule_end
                FROM deduped d
                CROSS JOIN biostar_employees be
                WHERE be.biostar_user_id = %s
                GROUP BY d.event_datetime::date, be.lunch_break_minutes, be.working_hours,
                         be.schedule_start, be.schedule_end
            ),
            adj_only AS (
                -- Adjustments for days WITHOUT punches (absent-day adjustments)
                SELECT adj.date,
                       NULL::timestamp AS first_punch,
                       NULL::timestamp AS last_punch,
                       0::bigint AS total_punches,
                       NULL::numeric AS duration_seconds,
                       be.lunch_break_minutes,
                       be.working_hours,
                       be.schedule_start AS static_schedule_start,
                       be.schedule_end AS static_schedule_end
                FROM biostar_daily_adjustments adj
                CROSS JOIN biostar_employees be
                WHERE adj.biostar_user_id = %s
                  AND be.biostar_user_id = %s
                  AND adj.date BETWEEN %s::date AND %s::date
                  AND adj.date NOT IN (SELECT date FROM daily)
            ),
            all_days AS (
                SELECT * FROM daily
                UNION ALL
                SELECT * FROM adj_only
            )
            SELECT d.date, d.first_punch, d.last_punch, d.total_punches,
                   d.duration_seconds, d.lunch_break_minutes, d.working_hours,
                   COALESCE(sd.program_start, d.static_schedule_start) AS schedule_start,
                   COALESCE(sd.program_end, d.static_schedule_end) AS schedule_end,
                   sd.sincron_company,
                   sd.sincron_day_schedule,
                   adj.adjusted_first_punch,
                   adj.adjusted_last_punch,
                   adj.adjustment_type
            FROM all_days d
            LEFT JOIN biostar_employees be2 ON be2.biostar_user_id = %s
            LEFT JOIN LATERAL (
                SELECT st.program_in AS program_start,
                       st.program_out AS program_end,
                       COALESCE(co.company, se.company_name) AS sincron_company,
                       (SELECT json_agg(sub ORDER BY sub.norma DESC NULLS LAST)
                        FROM (
                            SELECT COALESCE(co2.company, se2.company_name) AS company,
                                   to_char(st2.program_in, 'HH24:MI') AS start,
                                   to_char(st2.program_out, 'HH24:MI') AS "end",
                                   se2.norma_lucru AS norma
                            FROM sincron_employees se2
                            JOIN sincron_timesheets st2
                              ON st2.sincron_employee_id = se2.sincron_employee_id
                              AND st2.company_name = se2.company_name
                              AND st2.day = d.date
                              AND st2.short_code IN ('OZ', 'OS')
                              AND st2.program_in IS NOT NULL
                              AND st2.program_out IS NOT NULL
                            LEFT JOIN companies co2 ON co2.id = se2.company_id
                            WHERE se2.mapped_jarvis_user_id = be2.mapped_jarvis_user_id
                              AND se2.is_active = TRUE
                        ) sub
                       ) AS sincron_day_schedule
                FROM sincron_employees se
                JOIN sincron_timesheets st
                  ON st.sincron_employee_id = se.sincron_employee_id
                  AND st.company_name = se.company_name
                  AND st.day = d.date
                  AND st.short_code IN ('OZ', 'OS')
                  AND st.program_in IS NOT NULL
                  AND st.program_out IS NOT NULL
                LEFT JOIN companies co ON co.id = se.company_id
                WHERE se.mapped_jarvis_user_id = be2.mapped_jarvis_user_id
                  AND se.is_active = TRUE
                ORDER BY se.norma_lucru DESC NULLS LAST
                LIMIT 1
            ) sd ON TRUE
            LEFT JOIN biostar_daily_adjustments adj
                ON adj.biostar_user_id = %s AND adj.date = d.date
            ORDER BY d.date DESC
        ''', (biostar_user_id, start_date, end_date, biostar_user_id,
              biostar_user_id, biostar_user_id, start_date, end_date,
              biostar_user_id, biostar_user_id))

    def get_employee_with_mapping(self, biostar_user_id):
        """Get employee details with JARVIS mapping info."""
        return self.query_one('''
            SELECT be.*,
                   u.name AS mapped_jarvis_user_name,
                   u.email AS mapped_jarvis_user_email
            FROM biostar_employees be
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
            WHERE be.biostar_user_id = %s
        ''', (biostar_user_id,))

    # ── Attendance Overview (stable employee list) ──

    def get_attendance_overview(self, date_str, jarvis_user_ids=None):
        """Get attendance overview for ALL active mapped employees on a given date.

        Unlike get_daily_summary which only shows employees with punches,
        this returns every active employee with NULL punch fields for absentees.
        """
        params = []
        user_filter = ''
        if jarvis_user_ids:
            user_filter = ' AND u.id = ANY(%s)'
            params.append(jarvis_user_ids)
        # date_str for deduped, adjustment JOIN, sincron schedule LATERAL, and leave-code LATERAL
        params.extend([date_str, date_str, date_str, date_str])
        return self.query_all(f'''
            WITH active_employees AS (
                SELECT DISTINCT ON (u.id)
                       u.id AS jarvis_user_id, u.name,
                       COALESCE(co.company, u.company) AS company,
                       u.department,
                       be.biostar_user_id, be.user_group_name, be.email,
                       be.lunch_break_minutes, be.working_hours,
                       be.schedule_start, be.schedule_end
                FROM users u
                JOIN biostar_employees be ON be.mapped_jarvis_user_id = u.id
                    AND be.status = 'active'
                    AND (be.is_blacklisted IS NULL OR be.is_blacklisted = FALSE)
                    AND (be.user_group_name IS NULL OR (be.user_group_name NOT ILIKE '%%plecati%%' AND be.user_group_name NOT ILIKE '%%contracte inchise%%'))
                LEFT JOIN companies co ON co.id = u.company_id
                WHERE u.is_active = TRUE
                  AND COALESCE(u.contract_status, 'active') != 'closed'{user_filter}
                ORDER BY u.id, be.last_synced_at DESC NULLS LAST
            ),
            deduped AS (
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime
                FROM biostar_punch_logs pl
                WHERE pl.event_datetime::date = %s::date
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            punch_summary AS (
                SELECT d.biostar_user_id,
                       MIN(d.event_datetime) AS first_punch,
                       MAX(d.event_datetime) AS last_punch,
                       COUNT(*) AS total_punches,
                       EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                GROUP BY d.biostar_user_id
            )
            SELECT ae.*,
                   ps.first_punch, ps.last_punch, ps.total_punches, ps.duration_seconds,
                   adj.adjusted_first_punch, adj.adjusted_last_punch, adj.adjustment_type,
                   CASE WHEN ps.biostar_user_id IS NULL THEN 'absent' ELSE 'present' END AS attendance_status,
                   sd.sincron_day_schedule,
                   sl.sincron_leave_code
            FROM active_employees ae
            LEFT JOIN punch_summary ps ON ps.biostar_user_id = ae.biostar_user_id
            LEFT JOIN biostar_daily_adjustments adj
                ON adj.biostar_user_id = ae.biostar_user_id AND adj.date = %s::date
            LEFT JOIN LATERAL (
                SELECT (SELECT json_agg(sub ORDER BY sub.norma DESC NULLS LAST)
                        FROM (
                            SELECT COALESCE(co2.company, se2.company_name) AS company,
                                   to_char(st2.program_in, 'HH24:MI') AS start,
                                   to_char(st2.program_out, 'HH24:MI') AS "end",
                                   se2.norma_lucru AS norma
                            FROM sincron_employees se2
                            JOIN sincron_timesheets st2
                              ON st2.sincron_employee_id = se2.sincron_employee_id
                              AND st2.company_name = se2.company_name
                              AND st2.day = %s::date
                              AND st2.short_code IN ('OZ', 'OS')
                              AND st2.program_in IS NOT NULL
                              AND st2.program_out IS NOT NULL
                            LEFT JOIN companies co2 ON co2.id = se2.company_id
                            WHERE se2.mapped_jarvis_user_id = ae.jarvis_user_id
                              AND se2.is_active = TRUE
                        ) sub
                       ) AS sincron_day_schedule
            ) sd ON TRUE
            LEFT JOIN LATERAL (
                SELECT st3.short_code AS sincron_leave_code
                FROM sincron_employees se3
                JOIN sincron_timesheets st3
                  ON st3.sincron_employee_id = se3.sincron_employee_id
                  AND st3.company_name = se3.company_name
                  AND st3.day = %s::date
                  AND st3.short_code IN ('CO','CM','CIC','CES','CMS','DLG','ZLS','CFP','CFS','INV')
                WHERE se3.mapped_jarvis_user_id = ae.jarvis_user_id
                  AND se3.is_active = TRUE
                LIMIT 1
            ) sl ON TRUE
            ORDER BY ae.company NULLS LAST,
                     CASE WHEN ps.biostar_user_id IS NULL THEN 1 ELSE 0 END,
                     ae.name
        ''', params)

    def get_attendance_week(self, end_date_str, jarvis_user_ids=None):
        """Get 7-day attendance summary for ALL active mapped employees.

        Returns each employee with days_present, days_absent, total_hours, etc.
        The 7-day window ends at end_date_str (inclusive) and goes back 6 days.
        """
        params = [end_date_str]
        user_filter = ''
        if jarvis_user_ids:
            user_filter = ' AND u.id = ANY(%s)'
            params.append(jarvis_user_ids)
        # end_date_str used again for punch window
        params.extend([end_date_str, end_date_str])
        return self.query_all(f'''
            WITH active_employees AS (
                SELECT DISTINCT ON (u.id)
                       u.id AS jarvis_user_id, u.name,
                       COALESCE(co.company, u.company) AS company,
                       u.department,
                       be.biostar_user_id, be.user_group_name, be.email,
                       be.lunch_break_minutes, be.working_hours,
                       be.schedule_start, be.schedule_end
                FROM users u
                JOIN biostar_employees be ON be.mapped_jarvis_user_id = u.id
                    AND be.status = 'active'
                    AND (be.is_blacklisted IS NULL OR be.is_blacklisted = FALSE)
                    AND (be.user_group_name IS NULL OR (be.user_group_name NOT ILIKE '%%plecati%%' AND be.user_group_name NOT ILIKE '%%contracte inchise%%'))
                LEFT JOIN companies co ON co.id = u.company_id
                WHERE u.is_active = TRUE
                  AND COALESCE(u.contract_status, 'active') != 'closed'{user_filter}
                ORDER BY u.id, be.last_synced_at DESC NULLS LAST
            ),
            deduped AS (
                SELECT DISTINCT ON (pl.biostar_user_id, date_trunc('minute', pl.event_datetime))
                    pl.biostar_user_id, pl.event_datetime
                FROM biostar_punch_logs pl
                WHERE pl.event_datetime::date BETWEEN (%s::date - INTERVAL '6 days')::date AND %s::date
                ORDER BY pl.biostar_user_id, date_trunc('minute', pl.event_datetime), pl.event_datetime ASC
            ),
            daily AS (
                SELECT
                    d.biostar_user_id,
                    d.event_datetime::date AS day,
                    MIN(d.event_datetime) AS first_punch,
                    MAX(d.event_datetime) AS last_punch,
                    COUNT(*) AS punches,
                    EXTRACT(EPOCH FROM (MAX(d.event_datetime) - MIN(d.event_datetime))) AS duration_seconds
                FROM deduped d
                GROUP BY d.biostar_user_id, d.event_datetime::date
            ),
            agg AS (
                SELECT
                    d.biostar_user_id,
                    COUNT(d.day) AS days_present,
                    SUM(d.duration_seconds) AS total_duration_seconds,
                    AVG(d.duration_seconds) AS avg_duration_seconds,
                    SUM(d.punches) AS total_punches,
                    AVG(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.first_punch::time) END) AS avg_check_in_epoch,
                    AVG(CASE WHEN d.punches > 1 THEN EXTRACT(EPOCH FROM d.last_punch::time) END) AS avg_check_out_epoch,
                    COUNT(adj.id) AS adjustment_count
                FROM daily d
                LEFT JOIN biostar_daily_adjustments adj
                    ON adj.biostar_user_id = d.biostar_user_id AND adj.date = d.day
                GROUP BY d.biostar_user_id
            )
            SELECT ae.*,
                   COALESCE(agg.days_present, 0) AS days_present,
                   7 - COALESCE(agg.days_present, 0) AS days_absent,
                   COALESCE(agg.total_duration_seconds, 0) AS total_duration_seconds,
                   COALESCE(agg.avg_duration_seconds, 0) AS avg_duration_seconds,
                   COALESCE(agg.total_punches, 0) AS total_punches,
                   agg.avg_check_in_epoch,
                   agg.avg_check_out_epoch,
                   COALESCE(agg.adjustment_count, 0) AS adjustment_count
            FROM active_employees ae
            LEFT JOIN agg ON agg.biostar_user_id = ae.biostar_user_id
            ORDER BY ae.company NULLS LAST, ae.name
        ''', params)

    # ── Devices ──

    def get_devices(self):
        """Get all unique devices from punch logs with stats."""
        return self.query_all('''
            SELECT device_name,
                   COUNT(*) AS punch_count,
                   COUNT(DISTINCT biostar_user_id) AS unique_users,
                   MIN(event_datetime) AS first_seen,
                   MAX(event_datetime) AS last_seen
            FROM biostar_punch_logs
            WHERE device_name IS NOT NULL AND device_name != ''
            GROUP BY device_name
            ORDER BY punch_count DESC
        ''')

    def backfill_directions(self, directions):
        """Update direction on existing punch logs based on device→direction mapping.

        Args:
            directions: dict of {device_name: 'IN'|'OUT'}

        Returns: total number of updated rows.
        """
        total = 0
        for device_name, direction in directions.items():
            if direction not in ('IN', 'OUT'):
                continue
            result = self.execute('''
                UPDATE biostar_punch_logs
                SET direction = %s
                WHERE device_name = %s AND (direction IS NULL OR direction != %s)
            ''', (direction, device_name, direction))
            if result:
                total += result if isinstance(result, int) else 0
        return total

    def get_employee_by_jarvis_user(self, jarvis_user_id):
        """Return active BioStar employee mapped to a JARVIS user ID, or None."""
        return self.query_one(
            '''SELECT biostar_user_id, name AS user_name, user_group_name,
                      (status = 'active') AS is_active,
                      lunch_break_minutes, working_hours, schedule_start, schedule_end,
                      mapped_jarvis_user_id
               FROM biostar_employees
               WHERE mapped_jarvis_user_id = %s AND status = 'active'
               LIMIT 1''',
            (jarvis_user_id,)
        )

    # ── JARVIS Users (for mapping) ──

    def get_jarvis_users(self):
        """Get all active JARVIS users for mapping."""
        return self.query_all(
            "SELECT id, name, email, department, company FROM users WHERE is_active = TRUE ORDER BY name"
        )
