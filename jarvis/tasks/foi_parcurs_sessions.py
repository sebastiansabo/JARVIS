"""Background job: Test Drive session lifecycle.

Every 10 minutes — (1) push the consilier once when a PLANNED session's start
hour is missed (still inside the 8h grace), (2) archive sessions past the grace
to MISSED (which frees the vehicle in conflict checks), (3) nudge the consilier
(and CC the brand inbox) when an active session's scheduled return passed >1h
ago and was never recorded. All passes idempotent.
"""
import html as _html

from core.utils.logging_config import get_logger
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from foi_parcurs.dealer_config import get_dealer_config
from core.notifications.notify import notify_with_push
from core.services.notification_service import send_email

logger = get_logger('jarvis.tasks.foi_parcurs_sessions')

_OVERDUE_TITLE = 'Retur întârziat — sesiune driving nepredată'


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
    ret = row.get('return_datetime')
    when = ret.strftime('%d.%m %H:%M') if hasattr(ret, 'strftime') else str(ret or '')
    hrs = row.get('overdue_hours')
    late = f' (întârziat cu ~{hrs}h)' if hrs else ''
    text = (f'Test drive {client} — {veh} trebuia predat la {when}{late}. '
            'Înregistrează returul.')
    link_path = f"/sales/test-drive/{row['id']}"
    body_html = (f'<p>{_html.escape(text)}</p>'
                 f'<p><a href="https://jarvis.autoworld.ro{link_path}">Deschide sesiunea</a></p>')
    return text, body_html


def notify_overdue_returns():
    """Pass 3: for each active TD session past its return time (>1h) with no
    return recorded, nudge the consilier (in-app + push + email) and CC the
    brand's configured dealer inbox. Re-fires are gated in SQL by a 4h cooldown;
    each session is isolated so one failure doesn't abort the rest."""
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
