"""HR attendance scheduled tasks — missing punch detection & notifications."""
import hashlib
import logging

logger = logging.getLogger('jarvis.tasks.hr_attendance')


def _stable_hash(key: str) -> int:
    """Deterministic hash that survives process restarts (unlike Python's hash())."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 2147483647


def check_missing_punches():
    """Daily check for missing punches — notify managers + HR.

    Runs at 10:00 AM (after BioStar sync at 01:00).
    Skips weekends (on Monday, also checks Friday).
    Respects per-employee notify_missing_punch toggle.
    Uses smart_notification_state for 24h cooldown per employee+date.
    """
    from datetime import date, timedelta

    today = date.today()
    # Build list of days to check: yesterday, plus Friday if today is Monday
    days_to_check = []
    yesterday = today - timedelta(days=1)
    if yesterday.weekday() < 5:  # Mon-Fri
        days_to_check.append(yesterday)
    if today.weekday() == 0:  # Monday — also check Friday
        friday = today - timedelta(days=3)
        if friday not in days_to_check:
            days_to_check.append(friday)

    # Filter out public holidays
    try:
        from core.utils.holidays_repository import HolidayRepository
        _hol_repo = HolidayRepository()
        days_to_check = [d for d in days_to_check if not _hol_repo.is_holiday(d)]
    except Exception:
        pass  # If holiday check fails, proceed with all days

    if not days_to_check:
        logger.debug("Skipping missing punch check — no weekdays to check")
        return

    try:
        from hr.events.repositories.employee_overview_repository import EmployeeOverviewRepository
        from core.notifications.notify import notify_users, notify_node_cascade
        from database import get_db, get_cursor, release_db

        repo = EmployeeOverviewRepository()
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            for check_date in days_to_check:
                _process_missing_for_date(check_date, repo, cursor, conn)

            conn.commit()
        finally:
            release_db(conn)

    except Exception as e:
        logger.error(f"Missing punch check failed: {e}", exc_info=True)


def _process_missing_for_date(check_date, repo, cursor, conn):
    """Process missing punches for a single date."""
    from core.notifications.notify import notify_users, notify_node_cascade

    missing = repo.get_all_missing_punches_for_date(check_date)

    if not missing:
        logger.info(f"No missing punches for {check_date}")
        return

    logger.info(f"Found {len(missing)} employees with missing punches for {check_date}")

    # Cooldown check — batch lookup
    to_notify = []
    for emp in missing:
        entity_hash = _stable_hash(f"{emp['user_id']}_{check_date.isoformat()}")
        cursor.execute('''
            SELECT 1 FROM smart_notification_state
            WHERE alert_type = 'missing_punch'
              AND entity_type = 'user_date'
              AND entity_id = %s
              AND last_alerted_at > NOW() - INTERVAL '24 hours'
        ''', (entity_hash,))
        if not cursor.fetchone():
            to_notify.append(emp)

    if not to_notify:
        logger.info(f"All missing punch notifications already sent for {check_date} (cooldown)")
        return

    # Pre-fetch L0 and HR users per company (avoid N+1 inside the loop)
    company_l0 = {}  # company -> set of user_ids
    company_hr = {}  # company -> set of user_ids
    companies = {emp.get('company') for emp in to_notify if emp.get('company')}
    for comp in companies:
        cursor.execute('''
            SELECT cr.user_id FROM company_responsables cr
            JOIN companies c ON c.id = cr.company_id WHERE c.company = %s
        ''', (comp,))
        company_l0[comp] = {r['user_id'] for r in cursor.fetchall()}
        cursor.execute('''
            SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
            JOIN companies c ON c.id = u.company_id
            WHERE r.name = 'HR' AND c.company = %s AND u.is_active = TRUE
        ''', (comp,))
        company_hr[comp] = {r['id'] for r in cursor.fetchall()}

    # Send notifications for each employee
    date_str = check_date.strftime('%d %b %Y')
    for emp in to_notify:
        user_id = emp['user_id']
        user_name = emp['user_name']
        node_id = emp.get('node_id')
        company = emp.get('company')

        title = f"Pontaj lipsa: {user_name}"
        message = f"{user_name} nu are pontaj pentru {date_str} si nu are concediu sau invoire activ(a)."
        link = f"/app/hr/employees/{user_id}"

        notified_ids = set()
        any_sent = False

        # L1-L5: cascade up the structure_nodes hierarchy
        if node_id:
            try:
                result = notify_node_cascade(
                    node_id, title, message=message, link=link,
                    entity_type='user', entity_id=user_id,
                    type='warning', category='hr_attendance',
                )
                any_sent = True
                # Track notified IDs from cascade result if available
                if isinstance(result, (list, set)):
                    notified_ids.update(result)
            except Exception as e:
                logger.error(f"Failed cascade notify for {user_name} node {node_id}: {e}")

        # L0: company responsables (skip already notified)
        if company:
            try:
                l0_ids = [uid for uid in company_l0.get(company, set())
                          if uid not in notified_ids]
                if l0_ids:
                    notify_users(
                        l0_ids, title, message=message, link=link,
                        entity_type='user', entity_id=user_id,
                        type='warning', category='hr_attendance',
                    )
                    notified_ids.update(l0_ids)
                    any_sent = True
            except Exception as e:
                logger.error(f"Failed L0 notify for {user_name}: {e}")

        # HR role users in same company (skip already notified)
        if company:
            try:
                hr_ids = [uid for uid in company_hr.get(company, set())
                          if uid not in notified_ids]
                if hr_ids:
                    notify_users(
                        hr_ids, title, message=message, link=link,
                        entity_type='user', entity_id=user_id,
                        type='warning', category='hr_attendance',
                    )
                    any_sent = True
            except Exception as e:
                logger.error(f"Failed HR notify for {user_name}: {e}")

        # Record cooldown only if at least one notification was sent
        if any_sent:
            entity_hash = _stable_hash(f"{user_id}_{check_date.isoformat()}")
            cursor.execute('''
                INSERT INTO smart_notification_state
                    (alert_type, entity_type, entity_id, last_alerted_at, last_value)
                VALUES ('missing_punch', 'user_date', %s, NOW(), 0)
                ON CONFLICT (alert_type, entity_type, entity_id)
                DO UPDATE SET last_alerted_at = NOW()
            ''', (entity_hash,))

    logger.info(f"Sent missing punch notifications for {len(to_notify)} employees on {check_date}")


def send_pontaje_digest():
    """Daily pontaje digest — yesterday's in/out + today's check-in for all employees.

    Runs at 10:30 Romania time (after auto-adjust at 10:15).
    Sends CSV with yesterday's Checked In/Out/Duration and today's Checked In.
    """
    import io
    import csv
    from datetime import date, timedelta

    try:
        from core.notifications.repositories import NotificationRepository
        from core.services.notification_service import send_email, is_smtp_configured
        from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
        from core.connectors.sincron.repositories.sincron_repository import SincronRepository

        # Check settings
        notif_repo = NotificationRepository()
        settings = notif_repo.get_settings()
        if settings.get('pontaje_digest_enabled') != 'true':
            logger.debug("Pontaje digest disabled, skipping")
            return
        if settings.get('pontaje_digest_daily_enabled') == 'false':
            logger.debug("Daily pontaje digest disabled, skipping")
            return

        # Per-period recipients, fall back to global
        recipients_str = (
            settings.get('pontaje_digest_daily_recipients', '').strip()
            or settings.get('pontaje_digest_recipients', '').strip()
        )
        if not recipients_str:
            logger.debug("No daily pontaje digest recipients configured, skipping")
            return

        if not is_smtp_configured():
            logger.warning("SMTP not configured, cannot send pontaje digest")
            return

        recipients = [e.strip() for e in recipients_str.split(',') if e.strip()]
        if not recipients:
            return

        today = date.today()
        yesterday = today - timedelta(days=1)
        # Skip weekends: if today is Monday, yesterday = Friday
        if today.weekday() == 0:
            yesterday = today - timedelta(days=3)
        elif today.weekday() == 6:  # Saturday — skip
            logger.debug("Saturday, skipping pontaje digest")
            return
        elif today.weekday() == 0 and yesterday.weekday() == 5:  # Sunday — skip
            logger.debug("Sunday, skipping pontaje digest")
            return

        year, month = today.year, today.month

        bio_repo = BioStarRepository()

        # Fetch Sincron day codes for the month
        sincron_repo = SincronRepository()
        sincron_codes = {}  # (jarvis_user_id, date) -> short_code

        def _parse_day(d):
            """Ensure day is a date object (DB may return str)."""
            if isinstance(d, date):
                return d
            return date.fromisoformat(str(d)[:10])

        try:
            day_codes = sincron_repo.get_all_day_codes(year, month)
            for row in day_codes:
                key = (row['mapped_jarvis_user_id'], _parse_day(row['day']))
                if key not in sincron_codes or row['short_code'] != 'OZ':
                    sincron_codes[key] = row['short_code']
        except Exception as e:
            logger.warning(f"Failed to fetch Sincron day codes: {e}")
        # Also fetch previous month if yesterday is in a different month
        if yesterday.month != month:
            try:
                prev_codes = sincron_repo.get_all_day_codes(yesterday.year, yesterday.month)
                for row in prev_codes:
                    key = (row['mapped_jarvis_user_id'], _parse_day(row['day']))
                    if key not in sincron_codes or row['short_code'] != 'OZ':
                        sincron_codes[key] = row['short_code']
            except Exception:
                pass

        # Fetch yesterday's full summary (all employees, with adjustments)
        yesterday_data = []
        try:
            yesterday_data = bio_repo.get_daily_summary(yesterday.isoformat())
        except Exception as e:
            logger.warning(f"Failed to get yesterday summary for {yesterday}: {e}")

        # Collect all employees — deduplicated by JARVIS user (one row per person)
        all_employees = bio_repo.get_all_employees(active_only=True)
        employee_map = {}  # jarvis_user_id -> {name, group, bio_ids, ...}
        for emp in all_employees:
            bio_id = emp.get('biostar_user_id')
            jid = emp.get('mapped_jarvis_user_id')
            if not bio_id or not jid or not emp.get('jarvis_user_active'):
                continue
            if jid in employee_map:
                # Just add this bio_id to existing entry
                employee_map[jid]['bio_ids'].append(bio_id)
                continue
            employee_map[jid] = {
                'name': emp.get('mapped_jarvis_user_name') or emp.get('name', ''),
                'group': emp.get('user_group_name') or '',
                'jarvis_user_id': jid,
                'bio_ids': [bio_id],
            }

        # Build CSV: one row per employee
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        yesterday_label = yesterday.strftime('%a %d %b')
        writer.writerow([
            'Name', 'Group',
            f'Checked In ({yesterday_label})', f'Checked Out ({yesterday_label})',
            f'Duration ({yesterday_label})', f'Status ({yesterday_label})',
        ])

        sorted_employees = sorted(employee_map.values(), key=lambda x: x['name'])

        def _find_punch(data_list, bio_ids):
            """Find first punch entry matching any of the employee's bio_ids."""
            for entry in data_list:
                if entry.get('biostar_user_id') in bio_ids:
                    return entry
            return None

        for emp in sorted_employees:
            jid = emp['jarvis_user_id']
            bio_ids = set(emp['bio_ids'])

            # Yesterday
            ys = _find_punch(yesterday_data, bio_ids)
            y_in = ''
            y_out = ''
            y_dur = ''
            if ys:
                raw_in = ys.get('adjusted_first_punch') or ys.get('first_punch')
                raw_out = ys.get('adjusted_last_punch') or ys.get('last_punch')
                if raw_in:
                    y_in = _fmt_time(raw_in)
                if raw_out:
                    y_out = _fmt_time(raw_out)
                if raw_in and raw_out:
                    lunch = ys.get('lunch_break_minutes') or 60
                    if ys.get('adjusted_first_punch') and ys.get('adjusted_last_punch'):
                        dur_sec = _time_diff_sec(ys['adjusted_first_punch'], ys['adjusted_last_punch'])
                    else:
                        dur_sec = ys.get('duration_seconds') or 0
                    net = max(0, dur_sec - lunch * 60) if dur_sec > lunch * 60 else dur_sec
                    if net > 0:
                        y_dur = f"{int(net // 3600)}:{int((net % 3600) // 60):02d}"

            y_status = _resolve_status(y_in, jid, yesterday, sincron_codes)

            writer.writerow([
                emp['name'], emp['group'],
                y_in, y_out, y_dur, y_status,
            ])

        csv_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')
        date_label = today.strftime('%d %b %Y')
        filename = f"pontaje_digest_{today.isoformat()}.csv"

        # Send to each recipient
        present_yesterday = sum(1 for s in yesterday_data if s.get('first_punch'))

        html_body = (
            f"Pontaje Daily Digest — {date_label}<br><br>"
            f"Yesterday ({yesterday.strftime('%a %d %b')}): {present_yesterday} checked in<br>"
            f"Total employees: {len(employee_map)}"
        )

        sent_count = 0
        for email in recipients:
            ok, err = send_email(
                to_email=email,
                subject=f"Pontaje Digest — {date_label}",
                html_body=html_body,
                attachments=[(filename, csv_bytes)],
                skip_global_cc=True,
            )
            if ok:
                sent_count += 1
            else:
                logger.error(f"Failed to send pontaje digest to {email}: {err}")

        logger.info(f"Pontaje digest sent to {sent_count}/{len(recipients)} recipients ({len(employee_map)} employees)")

    except Exception as e:
        logger.error(f"Pontaje digest failed: {e}", exc_info=True)


def _resolve_status(checked_in, jarvis_user_id, day_key, sincron_codes):
    """Determine status for a day: Prezent / Sincron leave code / Absent.

    day_key: date object matching the key used when building sincron_codes.
    """
    if checked_in:
        return 'Prezent'
    if jarvis_user_id:
        code = sincron_codes.get((jarvis_user_id, day_key), '')
        if code and code != 'OZ':
            return code
    return 'Absent'


def _fmt_time(dt_str):
    """Format datetime string to HH:MM."""
    if not dt_str:
        return ''
    try:
        from datetime import datetime
        if 'T' in str(dt_str):
            dt = datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
            return dt.strftime('%H:%M')
        return str(dt_str)[:5]
    except Exception:
        return str(dt_str)[:5] if dt_str else ''


def _time_diff_sec(a, b):
    """Compute seconds between two datetime strings."""
    try:
        from datetime import datetime
        ta = datetime.fromisoformat(str(a).replace('Z', '+00:00'))
        tb = datetime.fromisoformat(str(b).replace('Z', '+00:00'))
        return max(0, (tb - ta).total_seconds())
    except Exception:
        return 0


def send_monthly_pontaje_summary():
    """End-of-month total pontaje — structured by Employee / Week / Day.

    Runs on the 1st of each month covering the previous month.
    CSV structure: Employee Name | Company | Group | Week | Date | Day |
                   Checked In | Checked Out | Duration (h) | Sincron Status
    """
    import io
    import csv
    import calendar
    from datetime import date, timedelta

    try:
        from core.notifications.repositories import NotificationRepository
        from core.services.notification_service import send_email, is_smtp_configured
        from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
        from core.connectors.sincron.repositories.sincron_repository import SincronRepository

        # Check settings
        notif_repo = NotificationRepository()
        settings = notif_repo.get_settings()
        if settings.get('pontaje_digest_enabled') != 'true':
            logger.debug("Pontaje digest disabled, skipping monthly summary")
            return
        if settings.get('pontaje_digest_monthly_enabled') == 'false':
            logger.debug("Monthly pontaje digest disabled, skipping")
            return

        # Per-period recipients, fall back to global
        recipients_str = (
            settings.get('pontaje_digest_monthly_recipients', '').strip()
            or settings.get('pontaje_digest_recipients', '').strip()
        )
        if not recipients_str:
            logger.debug("No pontaje digest recipients configured, skipping monthly summary")
            return

        if not is_smtp_configured():
            logger.warning("SMTP not configured, cannot send monthly pontaje summary")
            return

        recipients = [e.strip() for e in recipients_str.split(',') if e.strip()]
        if not recipients:
            return

        # Determine previous month
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_day_prev = first_of_this_month - timedelta(days=1)
        year = last_day_prev.year
        month = last_day_prev.month
        month_name = calendar.month_name[month]
        _, num_days = calendar.monthrange(year, month)

        # Build list of working days (Mon-Fri)
        working_days = []
        for d in range(1, num_days + 1):
            dt = date(year, month, d)
            if dt.weekday() < 5:  # Mon-Fri
                working_days.append(dt)

        # Filter out public holidays
        try:
            from core.utils.holidays_repository import HolidayRepository
            _hol_repo = HolidayRepository()
            working_days = [d for d in working_days if not _hol_repo.is_holiday(d)]
        except Exception:
            pass

        if not working_days:
            logger.info("No working days in previous month, skipping monthly summary")
            return

        bio_repo = BioStarRepository()

        # Fetch daily summaries for all working days
        daily_data = {}  # date -> list of employee summaries
        for wd in working_days:
            try:
                daily_data[wd] = bio_repo.get_daily_summary(wd.isoformat())
            except Exception as e:
                logger.warning(f"Failed to get summary for {wd}: {e}")
                daily_data[wd] = []

        # All employees — only those mapped to an active JARVIS user
        all_employees = bio_repo.get_all_employees(active_only=True)
        employee_map = {}  # jarvis_user_id -> {name, group, bio_ids, ...}
        for emp in all_employees:
            bio_id = emp.get('biostar_user_id')
            jid = emp.get('mapped_jarvis_user_id')
            if not bio_id or not jid or not emp.get('jarvis_user_active'):
                continue
            if jid in employee_map:
                employee_map[jid]['bio_ids'].append(bio_id)
                continue
            employee_map[jid] = {
                'name': emp.get('mapped_jarvis_user_name') or emp.get('name', ''),
                'company': emp.get('jarvis_company') or '',
                'group': emp.get('user_group_name') or '',
                'jarvis_user_id': jid,
                'bio_ids': [bio_id],
            }

        # Fetch Sincron day codes for the month
        sincron_repo = SincronRepository()
        sincron_codes = {}  # (jarvis_user_id, date) -> short_code

        def _parse_day_m(d):
            if isinstance(d, date):
                return d
            return date.fromisoformat(str(d)[:10])

        try:
            day_codes = sincron_repo.get_all_day_codes(year, month)
            for row in day_codes:
                key = (row['mapped_jarvis_user_id'], _parse_day_m(row['day']))
                if key not in sincron_codes or row['short_code'] != 'OZ':
                    sincron_codes[key] = row['short_code']
        except Exception as e:
            logger.warning(f"Failed to fetch Sincron day codes: {e}")

        # Compute ISO week numbers for grouping
        def _week_label(dt):
            iso_year, iso_week, _ = dt.isocalendar()
            return f"W{iso_week}"

        # Build CSV: one row per employee per working day, grouped by employee then week
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow([
            'Name', 'Group',
            'Week', 'Date', 'Day',
            'Checked In', 'Checked Out', 'Duration (h)', 'Status',
        ])

        sorted_employees = sorted(employee_map.values(), key=lambda x: x['name'])

        def _find_punch_monthly(data_list, bio_ids):
            """Find first punch entry matching any of the employee's bio_ids."""
            for entry in data_list:
                if entry.get('biostar_user_id') in bio_ids:
                    return entry
            return None

        total_rows = 0
        for emp in sorted_employees:
            jid = emp['jarvis_user_id']
            bio_ids = set(emp['bio_ids'])
            for wd in working_days:
                week = _week_label(wd)
                day_name = wd.strftime('%a')
                date_str = wd.strftime('%d %b')

                # Find punch data for this employee on this day
                day_entries = daily_data.get(wd, [])
                entry = _find_punch_monthly(day_entries, bio_ids)

                checked_in = ''
                checked_out = ''
                duration = ''
                if entry:
                    raw_in = entry.get('adjusted_first_punch') or entry.get('first_punch')
                    raw_out = entry.get('adjusted_last_punch') or entry.get('last_punch')
                    if raw_in:
                        checked_in = _fmt_time(raw_in)
                    if raw_out:
                        checked_out = _fmt_time(raw_out)
                    if raw_in and raw_out:
                        lunch = entry.get('lunch_break_minutes') or 60
                        if entry.get('adjusted_first_punch') and entry.get('adjusted_last_punch'):
                            dur_sec = _time_diff_sec(entry['adjusted_first_punch'], entry['adjusted_last_punch'])
                        else:
                            dur_sec = entry.get('duration_seconds') or 0
                        net = max(0, dur_sec - lunch * 60) if dur_sec > lunch * 60 else dur_sec
                        if net > 0:
                            duration = f"{int(net // 3600)}:{int((net % 3600) // 60):02d}"

                status = _resolve_status(checked_in, jid, wd, sincron_codes)

                writer.writerow([
                    emp['name'], emp['group'],
                    week, date_str, day_name,
                    checked_in, checked_out, duration, status,
                ])
                total_rows += 1

        csv_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')
        filename = f"pontaje_total_{year}_{month:02d}.csv"

        # Summary stats
        total_employees = len(employee_map)
        total_working_days = len(working_days)

        html_body = (
            f"Pontaje Total — {month_name} {year}<br><br>"
            f"Total employees: {total_employees}<br>"
            f"Working days: {total_working_days}<br>"
            f"Total records: {total_rows}"
        )

        sent_count = 0
        for email in recipients:
            ok, err = send_email(
                to_email=email,
                subject=f"Pontaje Total — {month_name} {year}",
                html_body=html_body,
                attachments=[(filename, csv_bytes)],
                skip_global_cc=True,
            )
            if ok:
                sent_count += 1
            else:
                logger.error(f"Failed to send monthly pontaje summary to {email}: {err}")

        logger.info(f"Monthly pontaje summary sent to {sent_count}/{len(recipients)} recipients "
                     f"({total_employees} employees, {total_working_days} days, {total_rows} rows)")

    except Exception as e:
        logger.error(f"Monthly pontaje summary failed: {e}", exc_info=True)


_PRIMARY_CONTRACTS_CTE = '''
WITH primary_contracts AS (
    SELECT sincron_employee_id, company_name, mapped_jarvis_user_id
    FROM (
        SELECT se2.sincron_employee_id, se2.company_name, se2.mapped_jarvis_user_id,
               ROW_NUMBER() OVER (
                   PARTITION BY se2.mapped_jarvis_user_id
                   ORDER BY se2.norma_lucru DESC NULLS LAST, se2.company_name
               ) AS rn
        FROM sincron_employees se2
        WHERE se2.mapped_jarvis_user_id IS NOT NULL
          AND se2.is_active = TRUE
          AND se2.count_for_leave = TRUE
    ) ranked WHERE rn = 1
)
'''


def compute_hr_weekly_report_data(reference_date=None, period=None):
    """Compute all sections of the HR weekly digest.

    Args:
        reference_date: Override "today" for the computation.
        period: One of 'today', 'week', 'month', 'quarter', 'ytd' (default).
            Controls the date range for leave counting and punch data.

    Returns a JSON-serializable dict used by both the email digest
    and the Reports API endpoint.
    """
    from datetime import date, timedelta
    from collections import defaultdict
    from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    from hr.co_balance.repository import CoBalanceRepository
    from core.utils.work_calendar import get_working_days_range
    from core.base_repository import BaseRepository

    today = reference_date or date.today()
    year = today.year
    jan1 = date(year, 1, 1)
    period = period or 'ytd'

    # Compute date ranges based on period
    if period == 'today':
        period_start = today
        period_end = today
        punch_start = today
        punch_end = today
    elif period == 'week':
        period_start = today - timedelta(days=today.weekday())  # Monday
        period_end = today
        punch_start = period_start
        punch_end = today
    elif period == 'month':
        period_start = date(year, today.month, 1)
        period_end = today
        punch_start = period_start
        punch_end = today
    elif period == 'quarter':
        q_month = ((today.month - 1) // 3) * 3 + 1
        period_start = date(year, q_month, 1)
        period_end = today
        punch_start = period_start
        punch_end = today
    else:  # ytd (default, also used by email digest)
        period_start = jan1
        period_end = today
        # For YTD, punch data uses last full week
        punch_start = today - timedelta(days=today.weekday() + 7)
        punch_end = punch_start + timedelta(days=4)

    working_days = get_working_days_range(punch_start, punch_end)

    # Build period label
    _period_labels = {
        'today': f"Azi ({today.strftime('%d %b %Y')})",
        'week': f"Săptămâna curentă ({period_start.strftime('%d %b')} – {today.strftime('%d %b %Y')})",
        'month': f"{today.strftime('%B %Y')}",
        'quarter': f"T{((today.month - 1) // 3) + 1} {year} ({period_start.strftime('%d %b')} – {today.strftime('%d %b %Y')})",
        'ytd': f"YTD {year}",
    }
    period_label = _period_labels.get(period, f"YTD {year}")
    # Week label for backward compat with email digest
    week_num = punch_start.isocalendar()[1]
    week_label = f"W{week_num} ({punch_start.strftime('%d %b')} – {punch_end.strftime('%d %b %Y')})"

    _base = BaseRepository()
    sincron_repo = SincronRepository()
    bio_repo = BioStarRepository()
    co_repo = CoBalanceRepository()

    # Build canonical company name map (any variant → canonical from companies table)
    canonical_rows = _base.query_all('SELECT company FROM companies ORDER BY company')
    _canonical_names = [r['company'] for r in canonical_rows]
    _norm_cache = {}

    def _normalize_company(raw_name):
        """Map any company name variant to the canonical form."""
        if not raw_name:
            return raw_name
        if raw_name in _norm_cache:
            return _norm_cache[raw_name]
        # Exact match first
        for c in _canonical_names:
            if c == raw_name:
                _norm_cache[raw_name] = c
                return c
        # Case-insensitive match
        upper = raw_name.upper().replace(' S.R.L.', '').replace(' SRL', '').strip()
        for c in _canonical_names:
            if c.upper().replace(' S.R.L.', '').replace(' SRL', '').strip() == upper:
                _norm_cache[raw_name] = c
                return c
        # Prefix match (e.g. "AUTOWORLD INTERNATIONAL" → "Autoworld INTERNATIONAL S.R.L.")
        for c in _canonical_names:
            if c.upper().startswith(upper) or upper.startswith(c.upper().replace(' S.R.L.', '').replace(' SRL', '').strip()):
                _norm_cache[raw_name] = c
                return c
        _norm_cache[raw_name] = raw_name
        return raw_name

    # Build primary company map (user_id → main company name)
    primary_rows = _base.query_all(_PRIMARY_CONTRACTS_CTE + '''
        SELECT mapped_jarvis_user_id, company_name FROM primary_contracts
    ''')
    primary_company_map = {r['mapped_jarvis_user_id']: r['company_name'] for r in primary_rows}

    # ── Section 1: Leave days (CO only) by company (main contract) ──
    leave_codes = ('CO',)
    leave_by_company = _base.query_all(_PRIMARY_CONTRACTS_CTE + '''
        SELECT pc.company_name,
               COUNT(DISTINCT (pc.mapped_jarvis_user_id, st.day)) AS total_leave_days,
               COUNT(DISTINCT pc.mapped_jarvis_user_id) AS employees_with_leave
        FROM sincron_timesheets st
        JOIN primary_contracts pc
          ON pc.sincron_employee_id = st.sincron_employee_id
          AND pc.company_name = st.company_name
        WHERE st.short_code = ANY(%s)
          AND st.day >= %s AND st.day <= %s
        GROUP BY pc.company_name
        ORDER BY pc.company_name
    ''', (list(leave_codes), period_start.isoformat(), period_end.isoformat()))

    prev_leave_map = {}  # kept for email digest backward compat

    # Normalize leave_by_company company names
    for r in leave_by_company:
        r['company_name'] = _normalize_company(r['company_name'])

    # ── Section 2: Headcount by company (main contract only) ──
    headcount_rows = _base.query_all(_PRIMARY_CONTRACTS_CTE + '''
        SELECT company_name, COUNT(*) AS headcount
        FROM primary_contracts
        GROUP BY company_name
    ''')
    headcount_map = {}
    for r in headcount_rows:
        key = _normalize_company(r['company_name'])
        headcount_map[key] = headcount_map.get(key, 0) + int(r['headcount'])

    # Compute avg leave per employee
    leave_map = {}
    for r in leave_by_company:
        key = r['company_name']  # already normalized
        leave_map[key] = leave_map.get(key, 0) + int(r['total_leave_days'])
    avg_leave = []
    for company in sorted(headcount_map.keys()):
        hc = headcount_map[company]
        days = leave_map.get(company, 0)
        avg_leave.append({
            'company_name': company,
            'leave_days': days,
            'headcount': hc,
            'avg': round(days / hc, 1) if hc else 0,
        })

    # ── Section 3: Top 10 CO remaining (per company) ──
    all_co = co_repo.get_all_for_year(year)
    used_by_company = co_repo.get_used_ytd_by_user_company(year)

    co_rows = []
    for row in all_co:
        uid = row['user_id']
        raw_company = row.get('company_name', '')
        company = _normalize_company(raw_company)
        total = int(row['total_available'] or 0)
        used = used_by_company.get(uid, {}).get(raw_company, 0)
        co_rows.append({
            'name': f"{row.get('prenume', '')} {row.get('nume', '')}".strip(),
            'company': company,
            'department': row.get('departament') or '',
            'total_available': total,
            'used': round(used, 1),
            'remaining': round(total - used, 1),
        })

    all_co_sorted = sorted(co_rows, key=lambda x: x['remaining'], reverse=True)
    # top_10_co kept for email digest backward compat
    top_10_co = all_co_sorted[:10]

    # CO remaining aggregated by company (for section 1 column)
    co_remaining_by_company = defaultdict(float)
    for cr in co_rows:
        co_remaining_by_company[cr['company']] += cr['remaining']

    # Aggregation by department from users table (organigram)
    dept_rows = _base.query_all('''
        SELECT u.id, u.department, u.company
        FROM users u
        WHERE u.is_active = TRUE AND u.department IS NOT NULL AND u.department != ''
    ''')
    # Build user_id -> department map
    user_dept_map = {}
    for dr in dept_rows:
        user_dept_map[dr['id']] = dr['department']

    # Build CO data keyed by user_id (from co_balance)
    co_by_user = {}
    for row in all_co:
        uid = row['user_id']
        if uid not in co_by_user:
            raw_company = row.get('company_name', '')
            total = int(row['total_available'] or 0)
            used = used_by_company.get(uid, {}).get(raw_company, 0)
            co_by_user[uid] = {'used': used, 'remaining': total - used}

    # Aggregate per department
    dept_stats = defaultdict(lambda: {'headcount': 0, 'used': 0.0, 'remaining': 0.0})
    for uid, dep in user_dept_map.items():
        ds = dept_stats[dep]
        ds['headcount'] += 1
        co = co_by_user.get(uid, {})
        ds['used'] += co.get('used', 0)
        ds['remaining'] += co.get('remaining', 0)

    # ── Section 4 & 5: Punch data for selected period ──
    range_data = bio_repo.get_range_summary(
        punch_start.isoformat(), punch_end.isoformat(),
    )

    company_times_raw = defaultdict(lambda: {
        'check_in_epochs': [], 'check_out_epochs': [],
        'actual_hours': 0.0, 'employee_count': 0,
    })

    for row in range_data:
        raw_company = row.get('jarvis_company')
        if not raw_company:
            continue
        company = _normalize_company(raw_company)
        stats = company_times_raw[company]
        stats['employee_count'] += 1

        avg_in = row.get('avg_check_in_epoch')
        avg_out = row.get('avg_check_out_epoch')
        if avg_in is not None:
            stats['check_in_epochs'].append(float(avg_in))
        if avg_out is not None:
            stats['check_out_epochs'].append(float(avg_out))

        total_dur = float(row.get('adjusted_total_duration_seconds') or row.get('total_duration_seconds') or 0)
        lunch = float(row.get('lunch_break_minutes') or 60)
        days_present = int(row.get('days_present') or 0)
        net = max(0, total_dur - lunch * 60 * days_present) / 3600
        stats['actual_hours'] += net

    # Potential hours per company
    all_employees = bio_repo.get_all_employees(active_only=True)
    company_potential = defaultdict(float)
    company_headcount_bio = defaultdict(int)
    seen_users = set()
    for emp in all_employees:
        uid = emp.get('mapped_jarvis_user_id')
        if uid and emp.get('jarvis_user_active') and uid not in seen_users:
            raw_company = emp.get('jarvis_company')
            if raw_company:
                company = _normalize_company(raw_company)
                wh = float(emp.get('working_hours') or 8)
                company_potential[company] += wh * working_days
                company_headcount_bio[company] += 1
                seen_users.add(uid)

    # Build serializable section 4
    def _epoch_to_hm(epoch_secs):
        h = int(epoch_secs // 3600)
        m = int((epoch_secs % 3600) // 60)
        return f"{h:02d}:{m:02d}"

    avg_checkin_checkout = []
    for company in sorted(company_times_raw.keys()):
        s = company_times_raw[company]
        ins = s['check_in_epochs']
        outs = s['check_out_epochs']
        avg_checkin_checkout.append({
            'company_name': company,
            'avg_in': _epoch_to_hm(sum(ins) / len(ins)) if ins else '-',
            'avg_out': _epoch_to_hm(sum(outs) / len(outs)) if outs else '-',
            'employee_count': s['employee_count'],
        })

    # Build serializable section 5
    all_companies = sorted(set(list(company_times_raw.keys()) + list(company_potential.keys())))
    actual_vs_potential = []
    total_actual = 0.0
    total_potential = 0.0
    for company in all_companies:
        actual = company_times_raw[company]['actual_hours'] if company in company_times_raw else 0
        potential = company_potential.get(company, 0)
        total_actual += actual
        total_potential += potential
        pct = round(actual / potential * 100) if potential > 0 else 0
        actual_vs_potential.append({
            'company_name': company,
            'actual_hours': round(actual, 1),
            'potential_hours': round(potential, 1),
            'utilization_pct': pct,
        })

    total_leave_days = sum(int(r['total_leave_days']) for r in leave_by_company)
    total_pct = round(total_actual / total_potential * 100) if total_potential > 0 else 0

    return {
        'year': year,
        'period': period,
        'period_label': period_label,
        'week_label': week_label,
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'punch_start': punch_start.isoformat(),
        'punch_end': punch_end.isoformat(),
        'working_days': working_days,
        # backward compat
        'last_monday': punch_start.isoformat(),
        'last_friday': punch_end.isoformat(),
        'working_days_week': working_days,
        'leave_by_company': [
            {
                'company_name': r['company_name'],
                'total_leave_days': int(r['total_leave_days']),
                'employees_with_leave': int(r['employees_with_leave']),
                'headcount': headcount_map.get(r['company_name'], 0),
                'avg_per_employee': round(
                    int(r['total_leave_days']) / headcount_map[r['company_name']], 1
                ) if headcount_map.get(r['company_name']) else 0,
                'prev_year_days': prev_leave_map.get(r['company_name'], 0),
                'co_remaining': round(co_remaining_by_company.get(r['company_name'], 0), 1),
            }
            for r in leave_by_company
        ],
        'leave_by_department': sorted([
            {
                'department': dep,
                'headcount': ds['headcount'],
                'total_leave_days': round(ds['used'], 1),
                'co_remaining': round(ds['remaining'], 1),
            }
            for dep, ds in dept_stats.items()
        ], key=lambda x: x['department']),
        'headcount_map': headcount_map,
        'avg_leave_per_employee': avg_leave,
        'top_10_co': top_10_co,
        'all_co_rows': all_co_sorted,
        'avg_checkin_checkout': avg_checkin_checkout,
        'actual_vs_potential': actual_vs_potential,
        'totals': {
            'total_leave_days': total_leave_days,
            'total_actual_hours': round(total_actual, 1),
            'total_potential_hours': round(total_potential, 1),
            'total_utilization_pct': total_pct,
        },
    }


def send_hr_weekly_digest():
    """Weekly HR summary — leave YTD, CO remaining, hours by company.

    Runs every Monday at 07:00 UTC (10:00 Romania).
    Sends an HTML email with 5 summary sections grouped by company.
    """
    try:
        from core.notifications.repositories import NotificationRepository
        from core.services.notification_service import send_email, is_smtp_configured

        notif_repo = NotificationRepository()
        settings = notif_repo.get_settings()
        if settings.get('hr_weekly_digest_enabled') != 'true':
            logger.debug("HR weekly digest disabled, skipping")
            return

        recipients_str = settings.get('hr_weekly_digest_recipients', '').strip()
        if not recipients_str:
            logger.debug("No HR weekly digest recipients, skipping")
            return
        if not is_smtp_configured():
            logger.warning("SMTP not configured, cannot send HR weekly digest")
            return

        recipients = [e.strip() for e in recipients_str.split(',') if e.strip()]
        if not recipients:
            return

        data = compute_hr_weekly_report_data()
        subject = f"HR Weekly Digest — {data['week_label']}"
        html = _build_hr_weekly_html(data)

        sent_count = 0
        for email_addr in recipients:
            ok, err = send_email(
                to_email=email_addr,
                subject=subject,
                html_body=html,
                skip_global_cc=True,
            )
            if ok:
                sent_count += 1
            else:
                logger.error(f"Failed to send HR weekly digest to {email_addr}: {err}")

        logger.info(f"HR weekly digest sent to {sent_count}/{len(recipients)} recipients")

    except Exception as e:
        logger.error(f"HR weekly digest failed: {e}", exc_info=True)


def _build_hr_weekly_html(data):
    """Build the HTML body for the HR weekly digest email."""
    week_label = data['week_label']
    year = data['year']
    leave_by_company = data['leave_by_company']
    headcount_map = data['headcount_map']
    top_10_co = data['top_10_co']
    avg_checkin_checkout = data['avg_checkin_checkout']
    actual_vs_potential = data['actual_vs_potential']
    totals = data['totals']

    hdr = (
        'style="background:#2563eb;color:#fff;padding:6px 10px;'
        'font-size:13px;text-align:left;border:1px solid #ddd"'
    )
    td = 'style="padding:6px 10px;font-size:13px;border:1px solid #eee"'
    td_r = 'style="padding:6px 10px;font-size:13px;border:1px solid #eee;text-align:right"'
    row_alt = 'style="background:#f8fafc"'

    parts = []
    parts.append(
        f'<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto">'
        f'<div style="background:#2563eb;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0">'
        f'<h2 style="margin:0;font-size:18px">JARVIS — HR Weekly Digest</h2>'
        f'<p style="margin:4px 0 0;font-size:13px;opacity:0.9">{week_label}</p>'
        f'</div>'
        f'<div style="padding:20px;background:#fff;border:1px solid #e2e8f0;border-top:none">'
    )

    # ── Section 1: Leave Days YTD ──
    parts.append(f'<h3 style="color:#1e40af;font-size:15px;margin:0 0 8px">1. Zile Concediu YTD ({year})</h3>')
    parts.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px">')
    parts.append(f'<tr><th {hdr}>Companie</th><th {hdr}>Zile Concediu</th><th {hdr}>{year - 1}</th><th {hdr}>Angajați</th><th {hdr}>Medie/Ang.</th></tr>')
    for i, row in enumerate(leave_by_company):
        r = row_alt if i % 2 else ''
        prev = row.get('prev_year_days', 0)
        parts.append(
            f'<tr {r}><td {td}>{row["company_name"]}</td>'
            f'<td {td_r}>{row["total_leave_days"]}</td>'
            f'<td {td_r} style="padding:6px 10px;font-size:13px;border:1px solid #eee;text-align:right;color:#6b7280">{prev if prev else "-"}</td>'
            f'<td {td_r}>{row["employees_with_leave"]}</td>'
            f'<td {td_r}>{row.get("avg_per_employee", 0)}</td></tr>'
        )
    prev_total = sum(row.get('prev_year_days', 0) for row in leave_by_company)
    parts.append(
        f'<tr style="font-weight:bold;background:#e2e8f0">'
        f'<td {td}>TOTAL</td><td {td_r}>{totals["total_leave_days"]}</td>'
        f'<td {td_r} style="padding:6px 10px;font-size:13px;border:1px solid #eee;text-align:right;color:#6b7280">{prev_total if prev_total else "-"}</td>'
        f'<td {td_r}></td><td {td_r}></td></tr>'
    )
    parts.append('</table>')

    # ── Section 2: Avg Leave per Employee ──
    parts.append(f'<h3 style="color:#1e40af;font-size:15px;margin:0 0 8px">2. Media Zile Concediu / Angajat ({year})</h3>')
    parts.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px">')
    parts.append(f'<tr><th {hdr}>Companie</th><th {hdr}>Zile Concediu</th><th {hdr}>Angajați</th><th {hdr}>Medie</th></tr>')
    for i, row in enumerate(data['avg_leave_per_employee']):
        r = row_alt if i % 2 else ''
        parts.append(
            f'<tr {r}><td {td}>{row["company_name"]}</td>'
            f'<td {td_r}>{row["leave_days"]}</td><td {td_r}>{row["headcount"]}</td>'
            f'<td {td_r}>{row["avg"]}</td></tr>'
        )
    parts.append('</table>')

    # ── Section 3: Top 10 CO Remaining ──
    parts.append(f'<h3 style="color:#1e40af;font-size:15px;margin:0 0 8px">3. Top 10 — CO Ramas ({year})</h3>')
    parts.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px">')
    parts.append(
        f'<tr><th {hdr}>#</th><th {hdr}>Nume</th><th {hdr}>Companie</th>'
        f'<th {hdr}>Total CO</th><th {hdr}>Folosit</th><th {hdr}>Ramas</th></tr>'
    )
    for i, co in enumerate(top_10_co):
        r = row_alt if i % 2 else ''
        parts.append(
            f'<tr {r}><td {td_r}>{i + 1}</td><td {td}>{co["name"]}</td>'
            f'<td {td}>{co["company"]}</td>'
            f'<td {td_r}>{co["total_available"]}</td>'
            f'<td {td_r}>{co["used"]}</td>'
            f'<td {td_r}><b>{co["remaining"]}</b></td></tr>'
        )
    parts.append('</table>')

    # ── Section 4: Avg Check-in/out ──
    parts.append(f'<h3 style="color:#1e40af;font-size:15px;margin:0 0 8px">4. Media Check-in / Check-out ({week_label})</h3>')
    parts.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px">')
    parts.append(f'<tr><th {hdr}>Companie</th><th {hdr}>Avg In</th><th {hdr}>Avg Out</th><th {hdr}>Angajați</th></tr>')
    for i, row in enumerate(avg_checkin_checkout):
        r = row_alt if i % 2 else ''
        parts.append(
            f'<tr {r}><td {td}>{row["company_name"]}</td>'
            f'<td {td_r}>{row["avg_in"]}</td><td {td_r}>{row["avg_out"]}</td>'
            f'<td {td_r}>{row["employee_count"]}</td></tr>'
        )
    parts.append('</table>')

    # ── Section 5: Actual vs Potential Hours ──
    parts.append(f'<h3 style="color:#1e40af;font-size:15px;margin:0 0 8px">5. Ore Lucrate vs Potențial ({week_label})</h3>')
    parts.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:20px">')
    parts.append(
        f'<tr><th {hdr}>Companie</th><th {hdr}>Ore Lucrate</th>'
        f'<th {hdr}>Ore Potențial</th><th {hdr}>Utilizare %</th></tr>'
    )
    for i, row in enumerate(actual_vs_potential):
        r = row_alt if i % 2 else ''
        pct = row['utilization_pct']
        color = '#16a34a' if pct >= 85 else '#ca8a04' if pct >= 70 else '#dc2626'
        parts.append(
            f'<tr {r}><td {td}>{row["company_name"]}</td>'
            f'<td {td_r}>{row["actual_hours"]}h</td><td {td_r}>{row["potential_hours"]}h</td>'
            f'<td {td_r}><span style="color:{color};font-weight:bold">{pct}%</span></td></tr>'
        )
    parts.append(
        f'<tr style="font-weight:bold;background:#e2e8f0">'
        f'<td {td}>TOTAL</td><td {td_r}>{totals["total_actual_hours"]}h</td>'
        f'<td {td_r}>{totals["total_potential_hours"]}h</td><td {td_r}>{totals["total_utilization_pct"]}%</td></tr>'
    )
    parts.append('</table>')

    # Footer
    parts.append(
        '<hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0">'
        '<p style="font-size:11px;color:#94a3b8;margin:0">'
        'JARVIS · Automated HR Weekly Digest</p>'
    )
    parts.append('</div></div>')

    return '\n'.join(parts)
