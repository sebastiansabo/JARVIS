"""Config-driven, best-effort buyback notifications.

notify_new_request(record)                  -> acquisition inbox (email)
notify_owner(record, event, actor_id, ...)  -> form creator (in-app/push/email)

Every path swallows its own exceptions: these run after the record/offer is
already committed, so a send failure must never surface as a 500.
"""
import logging

from buyback import lifecycle
from buyback.services.config import get_config

logger = logging.getLogger('jarvis.buyback.notifications')

_EVENT_GROUP = {
    'status_changed': 'notify_milestones',
    'inspection_updated': 'notify_inspection',
    'inspection_report_uploaded': 'notify_inspection',
}
_EVENT_LABEL = {
    'inspection_updated': 'Inspecție actualizată',
    'inspection_report_uploaded': 'Raport inspecție încărcat',
}


def _vehicle(record) -> str:
    return f"{record.get('brand') or ''} {record.get('model') or ''}".strip()


def notify_new_request(record) -> None:
    try:
        cfg = get_config(record.get('company_id'))
        if not cfg['enabled'] or not cfg['notify_new_request'] or not cfg['acquisition_emails']:
            return
        code = record.get('record_code') or record.get('id')
        vehicle = _vehicle(record)
        subject = f"[BuyBack] Solicitare nouă — {vehicle}".strip()
        text = (f"Solicitare nouă {code} ({vehicle}).\n"
                f"Vânzător: {record.get('seller_name') or '—'}\n"
                f"Consilier: {record.get('advisor_name') or '—'}")
        html = f"<p>{text.replace(chr(10), '<br>')}</p>"
        from core.services.notification_service import send_email
        for to in cfg['acquisition_emails']:
            try:
                send_email(to_email=to, subject=subject, html_body=html,
                           text_body=text, from_name='AUTOWORLD')
            except Exception:
                logger.exception('buyback new-request email to %s failed', to)
    except Exception:
        logger.exception('notify_new_request failed for record %s', record.get('id'))


def notify_owner(record, event, actor_id, new_status=None) -> None:
    try:
        owner = record.get('created_by')
        if owner is None or owner == actor_id:
            return
        cfg = get_config(record.get('company_id'))
        group = _EVENT_GROUP.get(event)
        if not cfg['enabled'] or not group or not cfg[group]:
            return

        rid = record.get('id')
        code = record.get('record_code') or rid
        if event == 'status_changed':
            label = lifecycle.STATUS_LABELS.get(new_status, new_status or '')
            title = f"BuyBack {code}: {label}"
        else:
            title = f"BuyBack {code}: {_EVENT_LABEL.get(event, event)}"
        message = _vehicle(record) or None
        link = f'/app/buyback/{rid}'

        if cfg['channel_in_app']:
            try:
                from core.notifications.repositories.in_app_repo import InAppNotificationRepository
                InAppNotificationRepository().create(
                    user_id=owner, title=title, message=message, link=link,
                    entity_type='buyback', entity_id=rid,
                )
            except Exception:
                logger.exception('buyback in-app notify failed (record %s)', rid)
        if cfg['channel_push']:
            try:
                from core.notifications.push_service import send_push_to_users
                send_push_to_users([owner], title, message or title, category='buyback')
            except Exception:
                logger.exception('buyback push notify failed (record %s)', rid)
        if cfg['channel_email']:
            try:
                from core.auth.repositories.user_repository import UserRepository
                from core.services.notification_service import send_email
                user = UserRepository().get_by_id(owner)
                email = (user or {}).get('email')
                if email:
                    send_email(to_email=email, subject=title,
                               html_body=f"<p>{title}</p><p>{message or ''}</p>",
                               text_body=f"{title}\n{message or ''}", from_name='AUTOWORLD')
            except Exception:
                logger.exception('buyback owner email failed (record %s)', rid)
    except Exception:
        logger.exception('notify_owner failed for record %s', record.get('id'))
