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
    Includes Sincron leave status codes.
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

        recipients_str = settings.get('pontaje_digest_recipients', '').strip()
        if not recipients_str:
            logger.debug("No pontaje digest recipients configured, skipping")
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

        # Fetch yesterday's full summary (all employees, with adjustments)
        yesterday_data = []
        try:
            yesterday_data = bio_repo.get_daily_summary(yesterday.isoformat())
        except Exception as e:
            logger.warning(f"Failed to get yesterday summary for {yesterday}: {e}")

        # Fetch today's summary (check-in only, day not over)
        today_data = []
        try:
            today_data = bio_repo.get_daily_summary(today.isoformat())
        except Exception as e:
            logger.warning(f"Failed to get today summary for {today}: {e}")

        # Collect all employees from both days + active employees list
        all_employees = bio_repo.get_all_employees(active_only=True)
        employee_map = {}  # biostar_user_id -> {name, company, group, jarvis_user_id}
        for emp in all_employees:
            bio_id = emp.get('biostar_user_id')
            if bio_id:
                employee_map[bio_id] = {
                    'name': emp.get('mapped_jarvis_user_name') or emp.get('name', ''),
                    'company': emp.get('jarvis_company') or '',
                    'group': emp.get('user_group_name') or '',
                    'jarvis_user_id': emp.get('mapped_jarvis_user_id'),
                }
        for s in yesterday_data + today_data:
            bio_id = s.get('biostar_user_id')
            if bio_id and bio_id not in employee_map:
                employee_map[bio_id] = {
                    'name': s.get('mapped_jarvis_user_name') or s.get('name', ''),
                    'company': s.get('jarvis_company') or '',
                    'group': s.get('user_group_name') or '',
                    'jarvis_user_id': s.get('mapped_jarvis_user_id'),
                }

        # Fetch Sincron day codes for yesterday + today
        sincron_repo = SincronRepository()
        sincron_codes = {}  # (jarvis_user_id, day_num) -> short_code
        try:
            day_codes = sincron_repo.get_all_day_codes(year, month)
            for row in day_codes:
                key = (row['mapped_jarvis_user_id'], row['day'])
                if key not in sincron_codes or row['short_code'] != 'OZ':
                    sincron_codes[key] = row['short_code']
        except Exception as e:
            logger.warning(f"Failed to fetch Sincron day codes: {e}")
        # Also fetch previous month if yesterday is in a different month
        if yesterday.month != month:
            try:
                prev_codes = sincron_repo.get_all_day_codes(yesterday.year, yesterday.month)
                for row in prev_codes:
                    key = (row['mapped_jarvis_user_id'], row['day'])
                    if key not in sincron_codes or row['short_code'] != 'OZ':
                        sincron_codes[key] = row['short_code']
            except Exception:
                pass

        # Build CSV: one row per employee
        # Columns: Name, Company, Group, Yesterday In, Yesterday Out, Yesterday Duration,
        #          Yesterday Sincron, Today In, Today Sincron
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        yesterday_label = yesterday.strftime('%a %d %b')
        today_label = today.strftime('%a %d %b')
        writer.writerow([
            'Name', 'Company', 'Group',
            f'Checked In ({yesterday_label})', f'Checked Out ({yesterday_label})',
            f'Duration ({yesterday_label})', f'Sincron ({yesterday_label})',
            f'Checked In ({today_label})', f'Sincron ({today_label})',
        ])

        sorted_employees = sorted(employee_map.items(), key=lambda x: x[1]['name'])

        for bio_id, emp in sorted_employees:
            # Yesterday
            ys = next((x for x in yesterday_data if x.get('biostar_user_id') == bio_id), None)
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
                        y_dur = f"{net / 3600:.2f}"

            # Yesterday Sincron code
            y_sincron = ''
            jid = emp.get('jarvis_user_id')
            if jid:
                y_sincron = sincron_codes.get((jid, yesterday.day), '')

            # Today (check-in only)
            ts = next((x for x in today_data if x.get('biostar_user_id') == bio_id), None)
            t_in = ''
            if ts:
                raw_in = ts.get('first_punch')  # No adjustment yet for today
                if raw_in:
                    t_in = _fmt_time(raw_in)

            # Today Sincron code
            t_sincron = ''
            if jid:
                t_sincron = sincron_codes.get((jid, today.day), '')

            writer.writerow([
                emp['name'], emp['company'], emp['group'],
                y_in, y_out, y_dur, y_sincron,
                t_in, t_sincron,
            ])

        csv_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')
        date_label = today.strftime('%d %b %Y')
        filename = f"pontaje_digest_{today.isoformat()}.csv"

        # Send to each recipient
        present_yesterday = sum(1 for s in yesterday_data if s.get('first_punch'))
        present_today = sum(1 for s in today_data if s.get('first_punch'))

        html_body = (
            f"Pontaje Daily Digest — {date_label}<br><br>"
            f"Yesterday ({yesterday.strftime('%a %d %b')}): {present_yesterday} checked in<br>"
            f"Today ({today.strftime('%a %d %b')}): {present_today} checked in so far<br>"
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

        # Check settings (reuse same settings as daily digest)
        notif_repo = NotificationRepository()
        settings = notif_repo.get_settings()
        if settings.get('pontaje_digest_enabled') != 'true':
            logger.debug("Pontaje digest disabled, skipping monthly summary")
            return

        recipients_str = settings.get('pontaje_digest_recipients', '').strip()
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

        # All active employees
        all_employees = bio_repo.get_all_employees(active_only=True)
        employee_map = {}  # biostar_user_id -> {name, company, group, jarvis_user_id}
        for emp in all_employees:
            bio_id = emp.get('biostar_user_id')
            if bio_id:
                employee_map[bio_id] = {
                    'name': emp.get('mapped_jarvis_user_name') or emp.get('name', ''),
                    'company': emp.get('jarvis_company') or '',
                    'group': emp.get('user_group_name') or '',
                    'jarvis_user_id': emp.get('mapped_jarvis_user_id'),
                }
        # Also pick up any employees from daily data not in the map
        for day_entries in daily_data.values():
            for s in day_entries:
                bio_id = s.get('biostar_user_id')
                if bio_id and bio_id not in employee_map:
                    employee_map[bio_id] = {
                        'name': s.get('mapped_jarvis_user_name') or s.get('name', ''),
                        'company': s.get('jarvis_company') or '',
                        'group': s.get('user_group_name') or '',
                        'jarvis_user_id': s.get('mapped_jarvis_user_id'),
                    }

        # Fetch Sincron day codes for the month
        sincron_repo = SincronRepository()
        sincron_codes = {}  # (jarvis_user_id, day_num) -> short_code
        try:
            day_codes = sincron_repo.get_all_day_codes(year, month)
            for row in day_codes:
                key = (row['mapped_jarvis_user_id'], row['day'])
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
            'Name', 'Company', 'Group', 'Week', 'Date', 'Day',
            'Checked In', 'Checked Out', 'Duration (h)', 'Sincron Status',
        ])

        sorted_employees = sorted(employee_map.items(), key=lambda x: x[1]['name'])

        total_rows = 0
        for bio_id, emp in sorted_employees:
            jid = emp.get('jarvis_user_id')
            for wd in working_days:
                week = _week_label(wd)
                day_name = wd.strftime('%a')
                date_str = wd.strftime('%d %b')

                # Find punch data for this employee on this day
                day_entries = daily_data.get(wd, [])
                entry = next((x for x in day_entries if x.get('biostar_user_id') == bio_id), None)

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
                            duration = f"{net / 3600:.2f}"

                sincron = ''
                if jid:
                    sincron = sincron_codes.get((jid, wd.day), '')

                writer.writerow([
                    emp['name'], emp['company'], emp['group'],
                    week, date_str, day_name,
                    checked_in, checked_out, duration, sincron,
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
