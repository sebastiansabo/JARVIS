"""Verification service — compares Sincron, BioStar, and JARVIS data for a given month."""

import uuid
import logging
from datetime import date, datetime, timezone
from calendar import monthrange

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.verification')

# Sincron leave/absence codes that mean the employee should NOT be present at work
SINCRON_LEAVE_CODES = {'CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV'}
# Code for public holidays in Sincron
SINCRON_HOLIDAY_CODE = 'X'
# Hours threshold to flag a discrepancy (Sincron work hours vs BioStar punched hours)
HOURS_MISMATCH_THRESHOLD = 2.0


class VerificationService:
    def __init__(self):
        self._repo = BaseRepository()

    # ── Public API ──

    def run_verification(self, year: int, month: int, triggered_by=None) -> dict:
        """Run a full verification for a given month. Returns the run result."""
        run_id = str(uuid.uuid4())
        self._create_run(run_id, year, month, triggered_by)
        try:
            discrepancies = self._compare(year, month, run_id)
            summary = self._summarize(discrepancies)
            self._complete_run(run_id, summary)
            logger.info(f"Verification {run_id} complete: {len(discrepancies)} discrepancies")
            return {'success': True, 'run_id': run_id, 'year': year, 'month': month,
                    'discrepancy_count': len(discrepancies), 'summary': summary}
        except Exception as e:
            self._fail_run(run_id, str(e))
            logger.exception(f"Verification {run_id} failed: {e}")
            raise

    def get_last_run(self, year: int, month: int) -> dict | None:
        row = self._repo.query_one(
            'SELECT * FROM verification_runs WHERE year=%s AND month=%s ORDER BY started_at DESC LIMIT 1',
            (year, month),
        )
        return dict(row) if row else None

    def get_discrepancies(self, run_id: str, include_resolved=False) -> list:
        extra = '' if include_resolved else 'AND NOT is_resolved'
        rows = self._repo.query_all(
            f'SELECT * FROM verification_discrepancies WHERE run_id=%s {extra} ORDER BY severity DESC, employee_name',
            (run_id,),
        )
        return [dict(r) for r in rows]

    def resolve_discrepancy(self, discrepancy_id: int, resolved_by: int, notes: str = '') -> bool:
        updated = self._repo.execute(
            '''UPDATE verification_discrepancies
               SET is_resolved=TRUE, resolved_by=%s, resolved_at=%s, notes=%s
               WHERE id=%s AND NOT is_resolved''',
            (resolved_by, datetime.now(timezone.utc), notes, discrepancy_id),
        )
        return bool(updated)

    # ── Core comparison ──

    def _compare(self, year: int, month: int, run_id: str) -> list:
        discrepancies = []

        # Load Sincron timesheets for this month (all companies)
        sincron_rows = self._repo.query_all('''
            SELECT se.mapped_jarvis_user_id, se.company_name,
                   se.nume || ' ' || se.prenume AS employee_name,
                   st.day, st.short_code, st.value
            FROM sincron_timesheets st
            JOIN sincron_employees se
              ON se.sincron_employee_id = st.sincron_employee_id
             AND se.company_name = st.company_name
            WHERE st.year = %s AND st.month = %s
              AND se.mapped_jarvis_user_id IS NOT NULL
              AND COALESCE(se.is_active, TRUE) = TRUE
        ''', (year, month))

        # Group Sincron data by (user_id, day)
        # sincron_by_user[uid] = {day: [short_code, ...]}
        sincron_by_user: dict[int, dict[date, list[str]]] = {}
        sincron_hours_by_user: dict[int, float] = {}
        employee_meta: dict[int, tuple[str, str]] = {}  # uid -> (name, company)

        for row in sincron_rows:
            uid = row['mapped_jarvis_user_id']
            day = row['day'] if isinstance(row['day'], date) else date.fromisoformat(str(row['day']))
            code = row['short_code']
            name = row['employee_name']
            company = row['company_name']
            employee_meta[uid] = (name, company)

            sincron_by_user.setdefault(uid, {}).setdefault(day, []).append(code)

            # Accumulate work hours (OZ = ore zilnice, OS = ore suplimentare)
            if code in ('OZ', 'OS') and row['value']:
                sincron_hours_by_user[uid] = sincron_hours_by_user.get(uid, 0.0) + float(row['value'])

        if not sincron_by_user:
            return []

        # Load BioStar adjusted summary for this month
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        biostar_rows = self._repo.query_all('''
            SELECT
                be.mapped_jarvis_user_id,
                bda.date,
                bda.adjusted_duration_seconds,
                bda.adjusted_first_punch,
                bda.adjusted_last_punch
            FROM biostar_daily_adjustments bda
            JOIN biostar_employees be ON be.biostar_user_id = bda.biostar_user_id
            WHERE bda.date BETWEEN %s AND %s
              AND be.mapped_jarvis_user_id IS NOT NULL
        ''', (first_day, last_day))

        biostar_by_user: dict[int, dict[date, dict]] = {}
        biostar_hours_by_user: dict[int, float] = {}
        for row in biostar_rows:
            uid = row['mapped_jarvis_user_id']
            day = row['date'] if isinstance(row['date'], date) else date.fromisoformat(str(row['date']))
            biostar_by_user.setdefault(uid, {})[day] = dict(row)
            if row['adjusted_duration_seconds']:
                biostar_hours_by_user[uid] = (
                    biostar_hours_by_user.get(uid, 0.0)
                    + row['adjusted_duration_seconds'] / 3600.0
                )

        # Also load raw punch log presence as fallback — employees without adjustments
        # still have raw punches; we shouldn't flag them as "no punch"
        raw_punch_rows = self._repo.query_all('''
            SELECT DISTINCT be.mapped_jarvis_user_id, pl.event_datetime::date AS day
            FROM biostar_punch_logs pl
            JOIN biostar_employees be ON be.biostar_user_id = pl.biostar_user_id
            WHERE pl.event_datetime::date BETWEEN %s AND %s
              AND be.mapped_jarvis_user_id IS NOT NULL
        ''', (first_day, last_day))

        raw_punch_days: dict[int, set[date]] = {}
        for row in raw_punch_rows:
            uid = row['mapped_jarvis_user_id']
            day = row['day'] if isinstance(row['day'], date) else date.fromisoformat(str(row['day']))
            raw_punch_days.setdefault(uid, set()).add(day)
            # Also accumulate raw hours for biostar_hours if no adjustment exists
            biostar_by_user.setdefault(uid, {}).setdefault(day, {})

        # Load JARVIS hr.events (approved leaves) for this month
        jarvis_leaves: dict[int, list[dict]] = {}
        try:
            leave_rows = self._repo.query_all('''
                SELECT e.user_id, e.start_date, e.end_date, e.event_type
                FROM hr_events e
                WHERE e.start_date <= %s AND e.end_date >= %s
                  AND e.status = 'approved'
                  AND e.event_type IN ('co', 'cm', 'ces', 'cic')
            ''', (last_day, first_day))
            for row in leave_rows:
                jarvis_leaves.setdefault(row['user_id'], []).append(dict(row))
        except Exception:
            pass  # hr_events may have different schema — skip JARVIS leave comparison

        # ── Check 1: Sincron leave day but employee punched in BioStar ──
        for uid, day_codes in sincron_by_user.items():
            name, company = employee_meta.get(uid, ('Unknown', ''))
            for day, codes in day_codes.items():
                is_leave = any(c in SINCRON_LEAVE_CODES for c in codes)
                if not is_leave:
                    continue
                biostar_day = biostar_by_user.get(uid, {}).get(day)
                if biostar_day and biostar_day.get('adjusted_duration_seconds', 0) > 1800:
                    discrepancies.append({
                        'run_id': run_id,
                        'jarvis_user_id': uid,
                        'company_name': company,
                        'employee_name': name,
                        'discrepancy_type': 'leave_but_punched',
                        'day': day,
                        'sincron_value': {'codes': codes},
                        'biostar_value': {
                            'duration_seconds': biostar_day['adjusted_duration_seconds'],
                            'first_punch': str(biostar_day.get('adjusted_first_punch', '')),
                            'last_punch': str(biostar_day.get('adjusted_last_punch', '')),
                        },
                        'jarvis_value': None,
                        'severity': 'warning',
                    })

        # ── Check 2: Sincron work day but no BioStar punches ──
        working_codes = {'OZ', 'OS'}
        for uid, day_codes in sincron_by_user.items():
            name, company = employee_meta.get(uid, ('Unknown', ''))
            for day, codes in day_codes.items():
                has_work = any(c in working_codes for c in codes)
                if not has_work:
                    continue
                # Skip weekends
                if day.weekday() >= 5:
                    continue
                # Has punch if: adjustment record with duration, OR any raw punch log entry
                biostar_day = biostar_by_user.get(uid, {}).get(day)
                has_adjustment = biostar_day and biostar_day.get('adjusted_duration_seconds')
                has_raw_punch = day in raw_punch_days.get(uid, set())
                if not has_adjustment and not has_raw_punch:
                    discrepancies.append({
                        'run_id': run_id,
                        'jarvis_user_id': uid,
                        'company_name': company,
                        'employee_name': name,
                        'discrepancy_type': 'work_day_no_punch',
                        'day': day,
                        'sincron_value': {'codes': codes},
                        'biostar_value': None,
                        'jarvis_value': None,
                        'severity': 'warning',
                    })

        # ── Check 3: Monthly hours mismatch (Sincron vs BioStar) ──
        all_uids = set(sincron_by_user.keys())
        for uid in all_uids:
            sincron_h = sincron_hours_by_user.get(uid, 0.0)
            biostar_h = biostar_hours_by_user.get(uid, 0.0)
            if sincron_h == 0 and biostar_h == 0:
                continue
            delta = abs(sincron_h - biostar_h)
            if delta > HOURS_MISMATCH_THRESHOLD:
                name, company = employee_meta.get(uid, ('Unknown', ''))
                discrepancies.append({
                    'run_id': run_id,
                    'jarvis_user_id': uid,
                    'company_name': company,
                    'employee_name': name,
                    'discrepancy_type': 'hours_mismatch',
                    'day': None,
                    'sincron_value': {'hours': round(sincron_h, 2)},
                    'biostar_value': {'hours': round(biostar_h, 2)},
                    'jarvis_value': {'delta': round(delta, 2)},
                    'severity': 'error' if delta > 8 else 'warning',
                })

        # ── Check 4: Employees in Sincron with no BioStar mapping ──
        unmapped = self._repo.query_all('''
            SELECT se.mapped_jarvis_user_id, se.company_name,
                   se.nume || ' ' || se.prenume AS employee_name
            FROM sincron_employees se
            WHERE se.mapped_jarvis_user_id IS NOT NULL
              AND COALESCE(se.is_active, TRUE) = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM biostar_employees be
                  WHERE be.mapped_jarvis_user_id = se.mapped_jarvis_user_id
              )
        ''', ())
        for row in unmapped:
            discrepancies.append({
                'run_id': run_id,
                'jarvis_user_id': row['mapped_jarvis_user_id'],
                'company_name': row['company_name'],
                'employee_name': row['employee_name'],
                'discrepancy_type': 'no_biostar_mapping',
                'day': None,
                'sincron_value': None,
                'biostar_value': None,
                'jarvis_value': None,
                'severity': 'info',
            })

        # Bulk insert
        if discrepancies:
            self._insert_discrepancies(discrepancies)

        return discrepancies

    def _insert_discrepancies(self, discrepancies: list):
        import json
        rows = [
            (
                d['run_id'], d['jarvis_user_id'], d['company_name'], d['employee_name'],
                d['discrepancy_type'], d['day'],
                json.dumps(d['sincron_value']) if d['sincron_value'] else None,
                json.dumps(d['biostar_value']) if d['biostar_value'] else None,
                json.dumps(d['jarvis_value']) if d['jarvis_value'] else None,
                d['severity'],
            )
            for d in discrepancies
        ]
        from psycopg2.extras import execute_values
        def _work(cursor):
            execute_values(cursor, '''
                INSERT INTO verification_discrepancies
                    (run_id, jarvis_user_id, company_name, employee_name,
                     discrepancy_type, day, sincron_value, biostar_value, jarvis_value, severity)
                VALUES %s
            ''', rows)
        self._repo.execute_many(_work)

    # ── Run lifecycle ──

    def _create_run(self, run_id, year, month, triggered_by):
        self._repo.execute(
            '''INSERT INTO verification_runs (run_id, year, month, status, triggered_by)
               VALUES (%s, %s, %s, 'running', %s)''',
            (run_id, year, month, triggered_by),
        )

    def _complete_run(self, run_id, summary):
        import json
        self._repo.execute(
            '''UPDATE verification_runs
               SET status='completed', finished_at=%s, summary=%s
               WHERE run_id=%s''',
            (datetime.now(timezone.utc), json.dumps(summary), run_id),
        )

    def _fail_run(self, run_id, error_message):
        self._repo.execute(
            '''UPDATE verification_runs
               SET status='failed', finished_at=%s, summary=%s
               WHERE run_id=%s''',
            (datetime.now(timezone.utc), f'{{"error": "{error_message[:200]}"}}', run_id),
        )

    def _summarize(self, discrepancies: list) -> dict:
        from collections import Counter
        types = Counter(d['discrepancy_type'] for d in discrepancies)
        severities = Counter(d['severity'] for d in discrepancies)
        companies = Counter(d['company_name'] for d in discrepancies if d['company_name'])
        return {
            'total': len(discrepancies),
            'by_type': dict(types),
            'by_severity': dict(severities),
            'by_company': dict(companies),
        }
