"""Weekly punch-compliance digest — scheduled sender.

Runs daily at 08:00 Europe/Bucharest (see tasks/cleanup.py). On most days it is a
no-op; it only sends when :func:`compute_report_window` returns a window:

  * **Monday**     → the previous full working week (Mon–Fri).
  * **day after a mid-week month-end** (month ends Mon–Thu) → a closing report for
    that month's partial week (Monday-of-that-week → month-end), so a month is never
    left half-reported. The following Monday's report then covers only the new
    month's days of the straddling week, avoiding double-counting.

Recipients + managers come from ``notification_settings``:
  * ``punch_compliance_digest_enabled``  == 'true'
  * ``punch_compliance_digest_config``   == JSON list of
        {"manager_user_id": int, "recipients": ["a@x", ...], "manager_name"?: str}
  * ``punch_compliance_digest_tolerance`` (optional, minutes; default 10)

Each manager's team is resolved from the Sincron organigram. Only raw BioStar
punches are used (manual corrections are ignored).
"""
import calendar
import json
from datetime import date, datetime, timedelta

from core.utils.logging_config import get_logger

logger = get_logger(__name__)

ATTACHMENT_NAME = 'Sinteza_pontaj.xlsx'


def _is_month_end(d):
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _today_bucharest():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Bucharest')).date()
    except Exception:
        return date.today()


def compute_report_window(run_date):
    """Return (start, end, kind) for a given run date, or (None, None, None).

    kind is 'weekly' or 'month_close'.
    """
    yesterday = run_date - timedelta(days=1)
    # Closing report the morning after a month that ended mid-week (Mon–Thu).
    if _is_month_end(yesterday) and yesterday.weekday() <= 3:
        start = yesterday - timedelta(days=yesterday.weekday())  # Monday of that week
        return start, yesterday, 'month_close'
    # Monday → previous full working week, minus any already-closed leading part.
    if run_date.weekday() == 0:
        prev_mon = run_date - timedelta(days=7)
        prev_fri = prev_mon + timedelta(days=4)
        start = prev_mon
        d = prev_mon
        while d <= prev_fri:
            if _is_month_end(d) and d.weekday() <= 3:
                start = d + timedelta(days=1)  # leading part already closed mid-week
                break
            d += timedelta(days=1)
        if start > prev_fri:
            return None, None, None  # whole week already covered by the closing report
        return start, prev_fri, 'weekly'
    return None, None, None


def previous_working_week(run_date):
    """The last full Mon–Fri before the week containing run_date (used for ad-hoc/test runs)."""
    this_mon = run_date - timedelta(days=run_date.weekday())
    prev_mon = this_mon - timedelta(days=7)
    return prev_mon, prev_mon + timedelta(days=4)


def _subject(manager_name, start, end, kind):
    period = f"{start.strftime('%d.%m')}–{end.strftime('%d.%m.%Y')}"
    if kind == 'month_close':
        return f"Raport pontaj {manager_name} — închidere lună ({period})"
    return f"Raport pontaj {manager_name} — săptămâna {period}"


def run_for_manager(manager_user_id, recipients, start, end, *, kind='weekly',
                    tolerance=10, override_user_ids=None, manager_name=None,
                    dry_run=False):
    """Build (and, unless dry_run, send) one manager's digest.

    Returns a dict with the computed data, subject, html and the xlsx bytes so
    callers (trigger route / tests) can preview without sending.
    """
    from core.connectors.biostar.services.punch_compliance_service import PunchComplianceService

    svc = PunchComplianceService()
    data = svc.compute_for_manager(manager_user_id, start, end, tolerance,
                                   override_user_ids=override_user_ids,
                                   manager_name=manager_name)
    html = svc.build_html(data)
    xlsx = svc.build_xlsx(data)
    subject = _subject(data['manager_name'], start, end, kind)

    result = {'data': data, 'subject': subject, 'html': html,
              'xlsx': xlsx, 'sent': 0, 'recipients': list(recipients or [])}
    if dry_run:
        return result

    from core.services.notification_service import send_email, is_smtp_configured
    if not is_smtp_configured():
        logger.warning("SMTP not configured, cannot send punch-compliance digest")
        return result
    for addr in result['recipients']:
        ok, err = send_email(
            to_email=addr,
            subject=subject,
            html_body=html,
            attachments=[(ATTACHMENT_NAME, xlsx)],
            skip_global_cc=True,
        )
        if ok:
            result['sent'] += 1
        else:
            logger.error(f"Punch-compliance digest to {addr} failed: {err}")
    logger.info(f"Punch-compliance digest for {data['manager_name']}: "
                f"sent {result['sent']}/{len(result['recipients'])}")
    return result


def send_punch_compliance_digest(reference_date=None):
    """Scheduled entry point — decides the window and fans out over configured managers."""
    try:
        from core.notifications.repositories import NotificationRepository

        run_date = reference_date or _today_bucharest()
        start, end, kind = compute_report_window(run_date)
        if start is None:
            logger.debug("Punch-compliance digest: no window for %s, skipping", run_date)
            return

        settings = NotificationRepository().get_settings()
        if settings.get('punch_compliance_digest_enabled') != 'true':
            logger.debug("Punch-compliance digest disabled, skipping")
            return
        try:
            config = json.loads(settings.get('punch_compliance_digest_config') or '[]')
        except (ValueError, TypeError):
            logger.error("Punch-compliance digest: invalid config JSON, skipping")
            return
        if not config:
            logger.debug("Punch-compliance digest: no managers configured")
            return
        try:
            tolerance = int(settings.get('punch_compliance_digest_tolerance') or 10)
        except (ValueError, TypeError):
            tolerance = 10

        for entry in config:
            mgr = entry.get('manager_user_id')
            recipients = entry.get('recipients') or []
            if not mgr or not recipients:
                continue
            try:
                run_for_manager(mgr, recipients, start, end, kind=kind,
                                tolerance=tolerance,
                                manager_name=entry.get('manager_name'))
            except Exception as e:
                logger.error("Punch-compliance digest for manager %s failed: %s",
                             mgr, e, exc_info=True)
    except Exception as e:
        logger.error(f"Punch-compliance digest failed: {e}", exc_info=True)
