"""Background job: Test Drive session lifecycle.

Every 10 minutes — (1) push the consilier once when a PLANNED session's start
hour is missed (still inside the 8h grace), (2) archive sessions past the grace
to MISSED (which frees the vehicle in conflict checks), (3) nudge the consilier
(and CC the brand inbox) when an active session's scheduled return passed >2h
ago and was never recorded — but only on weekdays between 08:00 and 18:00
(Europe/Bucharest), so nobody is pinged overnight or on a weekend. All passes
idempotent.
"""
import html as _html
from datetime import datetime as _datetime

from core.utils.logging_config import get_logger
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from foi_parcurs.dealer_config import get_dealer_config
from core.notifications.notify import notify_with_push
from core.services.notification_service import send_email

logger = get_logger('jarvis.tasks.foi_parcurs_sessions')

_OVERDUE_TITLE = 'Retur neînregistrat — sesiune driving deschisă'

# Overdue-return alerts are only sent during dealership working hours so the
# consilier is never pinged overnight or at the weekend. Weekdays only,
# 08:00 (inclusive) — 18:00 (exclusive), Europe/Bucharest.
_SEND_START_HOUR = 8
_SEND_END_HOUR = 18


def _within_send_window(now=None):
    """True only Mon–Fri, 08:00 ≤ time < 18:00 (Europe/Bucharest).

    Gates the overdue-return pass: a car that goes overdue overnight or on a
    weekend is held and first nudged at the next in-window scheduler tick, never
    at 3am. `now` is injectable for tests; production reads the Bucharest clock.
    Fails open (returns True) if the tz database is unavailable — better to alert
    than to silently swallow the nudge."""
    if now is None:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            return True
        now = _datetime.now(ZoneInfo('Europe/Bucharest'))
    if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return _SEND_START_HOUR <= now.hour < _SEND_END_HOUR


def _fmt_return_when(ret):
    """'%d.%m %H:%M' for a return_datetime that may be a datetime OR an ISO
    string. dict_from_row serializes timestamps to ISO ('2026-08-19T17:00:00+00:00'),
    so production never passes a datetime here. TD datetimes are Bucharest
    wall-clock stored as-is, so we format the stored digits verbatim — never
    convert timezone — which also drops the misleading +00:00 the ISO carries."""
    if hasattr(ret, 'strftime'):
        return ret.strftime('%d.%m %H:%M')
    if isinstance(ret, str) and ret:
        try:
            return _datetime.fromisoformat(ret).strftime('%d.%m %H:%M')
        except ValueError:
            return ret
    return ''


def _vehicle_label(row):
    """Human label for a session's car: 'Mark Model (PLATE)', else VIN."""
    name = ' '.join(p for p in ((row.get('mark') or '').strip(),
                                (row.get('model') or '').strip()) if p)
    plate = (row.get('registration_number') or '').strip()
    if plate:
        return f'{name} ({plate})'.strip()
    return name or (row.get('vin') or '').strip()


def _overdue_return_message(row):
    """(plain-text body, html body) for an overdue-return alert."""
    client = (row.get('client_name') or 'Client').strip()
    veh = _vehicle_label(row)
    when = _fmt_return_when(row.get('return_datetime'))
    hrs = row.get('overdue_hours')
    late = f' (de ~{hrs}h)' if hrs else ''
    text = (f'Test drive {client} — {veh}: returul programat la {when} nu a fost '
            f'încă înregistrat{late}. Verifică mașina și înregistrează returul.')
    link_path = f"/sales/test-drive/{row['id']}"
    body_html = (f'<p>{_html.escape(text)}</p>'
                 f'<p><a href="https://jarvis.autoworld.ro{link_path}">Deschide sesiunea</a></p>')
    return text, body_html


def notify_overdue_returns():
    """Pass 3: for each active TD session past its return time (>2h) with no
    return recorded, nudge the consilier (in-app + push + email) and CC the
    brand's configured dealer inbox. Only sends on weekdays 08:00–18:00
    (Europe/Bucharest); outside that window the pass is a no-op and the alert
    waits for the next in-window tick. Re-fires are gated in SQL by a 4h
    cooldown; each session is isolated so one failure doesn't abort the rest."""
    if not _within_send_window():
        return
    repo = FoiParcursRepository()
    for row in repo.get_overdue_return_sessions():
        try:
            uid = row.get('advisor_user_id')
            if not uid:
                logger.warning('overdue-return: unresolved advisor %r for session %s',
                               row.get('advisor_name'), row.get('id'))
                continue
            text, body_html = _overdue_return_message(row)
            link = f"/sales/test-drive/{row['id']}"
            notify_with_push(
                [uid], _OVERDUE_TITLE, text,
                link=link, push_data={'link': link},
                entity_type='foi_parcurs_td', entity_id=row['id'],
                category='system', type='warning',
            )
            email = (row.get('advisor_email') or '').strip()
            if email:
                cc = (get_dealer_config(row.get('company_name'),
                                        row.get('vehicle_brand')).get('email') or '').strip() or None
                try:
                    ok, err = send_email(to_email=email, subject=_OVERDUE_TITLE,
                                         html_body=body_html, text_body=text, department_cc=cc)
                    if not ok:
                        logger.warning('overdue-return email not sent for %s: %s', email, err)
                except Exception:
                    logger.warning('overdue-return email failed for %s', email, exc_info=True)
            repo.mark_overdue_return_notified(row['id'])
        except Exception:
            logger.warning('overdue-return notify failed for session %s',
                           row.get('id'), exc_info=True)


def run_session_lifecycle():
    try:
        repo = FoiParcursRepository()
        for row in repo.get_sessions_pending_late_notify():
            try:
                uid = repo.get_advisor_user_id(row.get('advisor_name'))
                if uid:
                    dep = row.get('departure_datetime')
                    when = dep.strftime('%H:%M') if dep else ''
                    client = (row.get('client_name') or 'Client').strip()
                    veh = (row.get('vin') or '').strip()
                    notify_with_push(
                        [uid],
                        'Sesiune ratată la start',
                        f'{client} — {veh} la {when}. Reprogramează sau activează.',
                        link=f"/sales/test-drive/{row['id']}",
                        push_data={'link': f"/sales/test-drive/{row['id']}"},
                        entity_type='foi_parcurs_td',
                        entity_id=row['id'],
                        category='system',
                    )
                repo.mark_late_notified(row['id'])
            except Exception:
                logger.warning('late-notify failed for session %s', row.get('id'), exc_info=True)

        count = repo.archive_missed_sessions()
        if count:
            logger.info('Archived %s missed TD session(s)', count)

        notify_overdue_returns()
    except Exception as e:
        logger.error('Session lifecycle job failed: %s', e, exc_info=True)
