"""Config-driven, best-effort buyback notifications.

notify_new_request(record)                  -> acquisition inbox (email)
notify_owner(record, event, actor_id, ...)  -> form creator (in-app/push/email)
notify_held(record, reason, note, actor)    -> issuer (email + in-app/push)

Every path swallows its own exceptions: these run after the record/offer is
already committed, so a send failure must never surface as a 500.
"""
import html as _html
import logging

from buyback import lifecycle
from buyback.seller_identity import seller_display_name
from buyback.services.config import get_config

logger = logging.getLogger('jarvis.buyback.notifications')


def _esc(value) -> str:
    """html.escape a value for safe interpolation into an email HTML body
    (record fields like seller_name/brand are user-controlled)."""
    return _html.escape('' if value is None else str(value))

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
        seller = seller_display_name(record) or '—'
        advisor = record.get('advisor_name') or '—'
        subject = f"[BuyBack] Solicitare nouă — {vehicle}".strip()
        text = (f"Solicitare nouă {code} ({vehicle}).\n"
                f"Vânzător: {seller}\n"
                f"Consilier: {advisor}")
        html_body = (
            f"<p>Solicitare nouă {_esc(code)} ({_esc(vehicle)}).<br>"
            f"Vânzător: {_esc(seller)}<br>"
            f"Consilier: {_esc(advisor)}</p>"
        )
        from core.services.notification_service import send_email

        # CC the submitter (the user who created the request) so they get a copy
        # of their own new-request notification. Resolved once and attached to a
        # single send (the first acquisition recipient) so they receive exactly
        # one copy regardless of how many acquisition inboxes are configured;
        # skipped when they're already an acquisition recipient (no duplicate).
        submitter_cc = None
        creator_id = record.get('created_by')
        if creator_id is not None:
            try:
                from core.auth.repositories.user_repository import UserRepository
                creator = UserRepository().get_by_id(creator_id)
                email = (creator or {}).get('email')
                if email and email not in cfg['acquisition_emails']:
                    submitter_cc = email
            except Exception:
                logger.exception('buyback new-request submitter CC lookup failed (record %s)',
                                 record.get('id'))

        for idx, to in enumerate(cfg['acquisition_emails']):
            try:
                send_email(to_email=to, subject=subject, html_body=html_body,
                           text_body=text, from_name='AUTOWORLD',
                           department_cc=submitter_cc if idx == 0 else None)
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
                               html_body=f"<p>{_esc(title)}</p><p>{_esc(message or '')}</p>",
                               text_body=f"{title}\n{message or ''}", from_name='AUTOWORLD')
            except Exception:
                logger.exception('buyback owner email failed (record %s)', rid)
    except Exception:
        logger.exception('notify_owner failed for record %s', record.get('id'))


def notify_held(record, reason, note, actor) -> None:
    """Best-effort notification to the issuing advisor/creator when a record
    is put ON_HOLD: an email carrying the reason + note, AND an in-app+push
    notification (core.notifications.notify.notify_user). Fires AFTER
    BuyBackService.hold() has already committed the hold — mirrors every
    other notifier in this module: each channel wraps its own body in
    try/except (log+swallow) so a send failure can never surface as a 500
    on an otherwise-successful hold.
    """
    rid = record.get('id')
    code = record.get('record_code') or rid
    message = reason + (f' — {note}' if note else '')

    # Email the advisor/creator — reuses email.py's internal-recipient
    # resolver (advisor_id, then created_by) the same way notify_sales does,
    # just with no department env-var override configured for this path.
    try:
        from buyback.services.email import _resolve_internal_recipient
        from core.services.notification_service import send_email

        to_email = _resolve_internal_recipient(record, 'BUYBACK_HOLD_EMAIL')
        if to_email:
            subject = f"BuyBack {code}: Solicitare suspendată".strip()
            text = f"Solicitarea {code} ({_vehicle(record)}) a fost suspendată.\nMotiv: {message}"
            html_body = (
                f"<p>Solicitarea {_esc(code)} ({_esc(_vehicle(record))}) a fost suspendată.</p>"
                f"<p>Motiv: {_esc(message)}</p>"
            )
            success, error = send_email(
                to_email=to_email, subject=subject, html_body=html_body,
                text_body=text, from_name='AUTOWORLD',
            )
            if not success:
                logger.warning(
                    'buyback hold email to %s failed (record %s): %s',
                    to_email, rid, error,
                )
        else:
            logger.info(
                'buyback record %s: no recipient resolvable for hold email', rid,
            )
    except Exception:
        logger.exception('notify_held email failed for record %s', rid)

    # In-app + push to the creator.
    try:
        creator = record.get('created_by')
        if creator:
            from core.notifications.notify import notify_user
            notify_user(
                creator, 'Solicitare BuyBack suspendată', message=message,
                link=f'/app/buyback/{rid}', entity_type='buyback_record',
                entity_id=rid, category='buyback',
            )
    except Exception:
        logger.exception('notify_held push/in-app failed for record %s', rid)
