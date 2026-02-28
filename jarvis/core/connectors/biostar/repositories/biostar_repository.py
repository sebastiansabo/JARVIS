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
                   u.name AS mapped_jarvis_user_name
            FROM biostar_employees be
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
        '''
        if active_only:
            sql += " WHERE be.status = 'active'"
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
                    ON CONFLICT (biostar_event_id) DO NOTHING
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

    def get_daily_summary(self, date_str):
        """Get per-employee daily punch summary with group, duration, mapped user, schedule."""
        return self.query_all('''
            SELECT
                pl.biostar_user_id,
                be.name,
                be.email,
                be.user_group_name,
                be.mapped_jarvis_user_id,
                u.name AS mapped_jarvis_user_name,
                be.lunch_break_minutes,
                be.working_hours,
                be.schedule_start,
                be.schedule_end,
                MIN(pl.event_datetime) AS first_punch,
                MAX(pl.event_datetime) AS last_punch,
                COUNT(*) AS total_punches,
                EXTRACT(EPOCH FROM (MAX(pl.event_datetime) - MIN(pl.event_datetime))) AS duration_seconds
            FROM biostar_punch_logs pl
            LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
            WHERE pl.event_datetime::date = %s::date
            GROUP BY pl.biostar_user_id, be.name, be.email, be.user_group_name,
                     be.mapped_jarvis_user_id, u.name, be.lunch_break_minutes, be.working_hours,
                     be.schedule_start, be.schedule_end
            ORDER BY be.name
        ''', (date_str,))

    def get_range_summary(self, start_date, end_date):
        """Get per-employee aggregated punch summary over a date range."""
        return self.query_all('''
            WITH daily AS (
                SELECT
                    pl.biostar_user_id,
                    pl.event_datetime::date AS day,
                    MIN(pl.event_datetime) AS first_punch,
                    MAX(pl.event_datetime) AS last_punch,
                    COUNT(*) AS punches,
                    EXTRACT(EPOCH FROM (MAX(pl.event_datetime) - MIN(pl.event_datetime))) AS duration_seconds
                FROM biostar_punch_logs pl
                WHERE pl.event_datetime::date BETWEEN %s::date AND %s::date
                GROUP BY pl.biostar_user_id, pl.event_datetime::date
            )
            SELECT
                d.biostar_user_id,
                be.name,
                be.email,
                be.user_group_name,
                be.mapped_jarvis_user_id,
                u.name AS mapped_jarvis_user_name,
                be.lunch_break_minutes,
                be.working_hours,
                be.schedule_start,
                be.schedule_end,
                COUNT(d.day) AS days_present,
                SUM(d.duration_seconds) AS total_duration_seconds,
                AVG(d.duration_seconds) AS avg_duration_seconds,
                SUM(d.punches) AS total_punches,
                MIN(d.first_punch) AS earliest_punch,
                MAX(d.last_punch) AS latest_punch
            FROM daily d
            LEFT JOIN biostar_employees be ON be.biostar_user_id = d.biostar_user_id
            LEFT JOIN users u ON u.id = be.mapped_jarvis_user_id
            GROUP BY d.biostar_user_id, be.name, be.email, be.user_group_name,
                     be.mapped_jarvis_user_id, u.name, be.lunch_break_minutes, be.working_hours,
                     be.schedule_start, be.schedule_end
            ORDER BY be.name
        ''', (start_date, end_date))

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
        """Get per-day punch summary for one employee over a date range."""
        return self.query_all('''
            SELECT
                pl.event_datetime::date AS date,
                MIN(pl.event_datetime) AS first_punch,
                MAX(pl.event_datetime) AS last_punch,
                COUNT(*) AS total_punches,
                EXTRACT(EPOCH FROM (MAX(pl.event_datetime) - MIN(pl.event_datetime))) AS duration_seconds,
                be.lunch_break_minutes,
                be.working_hours,
                be.schedule_start,
                be.schedule_end
            FROM biostar_punch_logs pl
            LEFT JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            WHERE pl.biostar_user_id = %s
              AND pl.event_datetime::date BETWEEN %s::date AND %s::date
            GROUP BY pl.event_datetime::date, be.lunch_break_minutes, be.working_hours,
                     be.schedule_start, be.schedule_end
            ORDER BY pl.event_datetime::date DESC
        ''', (biostar_user_id, start_date, end_date))

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

    # ── JARVIS Users (for mapping) ──

    def get_jarvis_users(self):
        """Get all active JARVIS users for mapping."""
        return self.query_all(
            "SELECT id, name, email, department, company FROM users WHERE is_active = TRUE ORDER BY name"
        )
