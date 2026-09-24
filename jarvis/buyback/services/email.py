"""Buyback offer + internal notification emails.

Two email flows fire when BuyBackService.post_offer() opens a new offer round
(Task 8's optional `notifier` hook, duck-typed: `send_offer_email(record,
offer)` + `notify_sales(record)`; `notify_acquisition(record)` is exposed too
for callers that want it, though post_offer() itself only calls the first
two — see buyback/services/buyback_service.py's Ruling R2 docstring):

  - send_offer_email: to the seller, built by build_offer_email() and sent
    via core.services.notification_service.send_email.
  - notify_sales / notify_acquisition: short internal heads-up emails to a
    configured department address (BUYBACK_SALES_EMAIL /
    BUYBACK_ACQUISITION_EMAIL env vars), falling back to the record's
    advisor/creator email if resolvable — see _resolve_internal_recipient().

Reuse, not reinvention (per the task brief): this module owns ZERO SMTP/MIME
plumbing of its own. It only:
  - calls core.services.notification_service.send_email for the actual send
    (SMTP config, MIME assembly, CC handling all live there already);
  - calls foi_parcurs.dealer_config.get_dealer_config for dealer contact
    details (address/phone/email) — the SAME helper foi_parcurs's test-drive
    overdue-return reminder email uses (tasks/foi_parcurs_sessions.py).

get_dealer_config()'s first arg is a company NAME string (it keys its DB/
built-in lookups by name — see tasks/foi_parcurs_sessions.py's
`get_dealer_config(row.get('company_name'), ...)` call and dealer_config.py's
`_norm()`), but a buyback record only carries `company_id`. _company_name()
below does a best-effort id->name lookup; on any failure (no DB, no match)
it returns None, and get_dealer_config(None, brand) degrades gracefully
(`_norm(None)` -> '', no match, no crash) rather than blowing up — it just
means the outgoing email's dealer-contact lines end up blank.

Non-fatal by design: BuyBackService.post_offer() has ALREADY committed the
offer + status transition (Task 8) by the time it calls into this module —
a bad SMTP config, a raising send_email, a dealer-lookup failure, none of it
may propagate back into post_offer() as an exception (that would surface as
a false-negative 500/409 on an offer that in fact posted successfully).
Every Notifier method below therefore wraps its ENTIRE body in try/except
and logs + swallows on failure; tests/buyback/test_email.py's
test_send_offer_email_swallows_raising_send_email is the regression test.
"""
import html
import os

from core.services.notification_service import send_email
from core.utils.logging_config import get_logger
from foi_parcurs.dealer_config import get_dealer_config

logger = get_logger('jarvis.buyback.email')

_OFFER_TYPE_LABELS = {'initial': 'inițială', 'final': 'finală'}

_SENDER_NAME = 'AUTOWORLD'


def _esc(value) -> str:
    """html.escape a value, tolerating None/non-str (Decimal, int, date)."""
    if value is None:
        return ''
    return html.escape(str(value))


def _company_name(company_id):
    """Best-effort company NAME lookup for `company_id` (see module
    docstring for why this is needed). Returns None on any failure — no
    company_id, no DB, no matching row — never raises."""
    if not company_id:
        return None
    try:
        from core.base_repository import BaseRepository
        row = BaseRepository().query_one(
            'SELECT company FROM companies WHERE id = %s', (company_id,)
        )
        return row['company'] if row else None
    except Exception:
        return None


def build_offer_email(record: dict, offer: dict, dealer: dict) -> tuple[str, str, str]:
    """Build (subject, text_body, html_body) for an offer-posted email to the
    seller.

    All record/offer/dealer values are `html.escape`d before being
    interpolated into the HTML. A row is omitted entirely when its backing
    value is missing/empty (e.g. no seller_name, no dealer phone) — per the
    brief's "omit lines whose value is missing".
    """
    dealer = dealer or {}
    brand = record.get('brand') or ''
    model = record.get('model') or ''
    vin = record.get('vin') or ''
    seller_name = record.get('seller_name') or ''
    amount_eur = offer.get('amount_eur')
    valid_until = offer.get('valid_until')
    offer_type = offer.get('offer_type')

    kind = _OFFER_TYPE_LABELS.get(offer_type, offer_type or '')
    subject = f"Ofertă {kind} — {brand} {model}".strip()
    dealer_name = dealer.get('name') or _SENDER_NAME
    greeting = f"Bună ziua {seller_name}," if seller_name else 'Bună ziua,'

    # (label, raw value) pairs, in display order. A pair is dropped entirely
    # when its value is falsy — the single source both the HTML table rows
    # and the plain-text lines below are derived from, so the two bodies can
    # never drift out of sync on which lines are shown.
    vehicle_bits = ' '.join(x for x in (brand, model) if x)
    pairs = []
    if vehicle_bits:
        pairs.append(('Vehicul', vehicle_bits))
    if vin:
        pairs.append(('VIN', vin))
    if amount_eur is not None:
        pairs.append(('Sumă ofertă', f'{amount_eur} €'))
    if valid_until:
        pairs.append(('Valabilă până la', str(valid_until)))
    if dealer.get('phone'):
        pairs.append(('Telefon dealer', dealer['phone']))
    if dealer.get('address'):
        pairs.append(('Adresă dealer', dealer['address']))
    if dealer.get('email'):
        pairs.append(('Email dealer', dealer['email']))

    rows_html = ''.join(
        f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;">{_esc(label)}</td>'
        f'<td style="padding:8px;border:1px solid #ddd;">{_esc(value)}</td></tr>'
        for label, value in pairs
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
            {_esc(subject)}
        </h2>
        <p>{_esc(greeting)}</p>
        <p>Vă transmitem oferta noastră {_esc(kind)} pentru vehiculul dumneavoastră:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            {rows_html}
        </table>
        <p>Pentru orice întrebare ne puteți contacta la datele de mai sus.</p>
        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        <p style="color: #666; font-size: 12px;">
            {_esc(dealer_name)}<br>
            Aceasta este o notificare automată din sistemul Jarvis.
        </p>
    </body>
    </html>
    """

    text_rows = '\n'.join(f'- {label}: {value}' for label, value in pairs)
    text_body = (
        f"{greeting}\n\n"
        f"Vă transmitem oferta noastră {kind} pentru vehiculul dumneavoastră:\n\n"
        f"{text_rows}\n\n"
        f"{dealer_name}\n"
        "Aceasta este o notificare automată din sistemul Jarvis."
    )

    return subject, text_body, html_body


def _resolve_internal_recipient(record: dict, env_var: str):
    """Recipient for an internal heads-up notification: a configured
    department address (env var) first, else the record's advisor, else its
    creator, if their user row resolves to an email. Returns None — the
    caller's no-op signal — when nothing resolves, per the brief's "keep
    simple; if no recipient resolvable, no-op"."""
    configured = (os.environ.get(env_var) or '').strip()
    if configured:
        return configured

    for uid in (record.get('advisor_id'), record.get('created_by')):
        if not uid:
            continue
        try:
            from core.auth.repositories.user_repository import UserRepository
            user = UserRepository().get_by_id(uid)
            email = (user or {}).get('email')
            if email:
                return email
        except Exception:
            continue
    return None


def _send_internal_notification(record: dict, env_var: str, label: str) -> None:
    """Shared body for notify_sales/notify_acquisition. Deliberately minimal
    (per the brief): a one-line status heads-up, no per-department CC lookup
    (buyback records carry no `department` field matching the legacy
    department_structure table get_department_cc_email keys off, so there is
    nothing meaningful to pass as `department_cc` here)."""
    to_email = _resolve_internal_recipient(record, env_var)
    if not to_email:
        logger.info(
            f"buyback record {record.get('id')}: no recipient resolvable for "
            f"{label} notification (set {env_var} or an advisor/creator "
            "email) — skipping"
        )
        return

    brand = record.get('brand') or ''
    model = record.get('model') or ''
    status = record.get('status') or ''
    subject = f"[Buyback] {label}: {brand} {model} — {status}".strip()
    body_text = (
        f"Record {record.get('record_code') or record.get('id')} "
        f"({brand} {model}) is now {status}."
    )
    html_body = f"<p>{_esc(body_text)}</p>"

    success, error = send_email(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=body_text,
        from_name=_SENDER_NAME,
    )
    if not success:
        logger.warning(
            f"buyback record {record.get('id')}: {label} notification to "
            f"{to_email} failed: {error}"
        )


class Notifier:
    """Fires BuyBackService.post_offer()'s notification hooks (Ruling R2:
    injected via `BuyBackService(notifier=...)`, duck-typed to
    `send_offer_email` + `notify_sales`; `notify_acquisition` is available
    too, for callers that want it).

    Every method below swallows its own exceptions (logs and returns) — see
    module docstring for why: post_offer() has already committed the offer +
    status transition by the time these run, so a notifier failure must
    never surface as a request-level 500.
    """

    def send_offer_email(self, record: dict, offer: dict) -> None:
        to_email = (record.get('seller_email') or '').strip()
        if not to_email:
            logger.info(
                f"buyback record {record.get('id')}: no seller_email — "
                "skipping offer email"
            )
            return
        try:
            dealer = get_dealer_config(
                _company_name(record.get('company_id')), record.get('brand')
            )
            subject, text_body, html_body = build_offer_email(record, offer, dealer)
            success, error = send_email(
                to_email=to_email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                from_name=_SENDER_NAME,
            )
            if not success:
                logger.warning(
                    f"buyback record {record.get('id')}: offer email to "
                    f"{to_email} failed: {error}"
                )
        except Exception:
            logger.exception(
                f"buyback record {record.get('id')}: offer email raised — "
                "swallowed so post_offer() is unaffected"
            )

    def notify_sales(self, record: dict) -> None:
        try:
            _send_internal_notification(record, 'BUYBACK_SALES_EMAIL', 'Sales')
        except Exception:
            logger.exception(
                f"buyback record {record.get('id')}: sales notification "
                "raised — swallowed so post_offer() is unaffected"
            )

    def notify_acquisition(self, record: dict) -> None:
        try:
            _send_internal_notification(record, 'BUYBACK_ACQUISITION_EMAIL', 'Acquisition')
        except Exception:
            logger.exception(
                f"buyback record {record.get('id')}: acquisition notification "
                "raised — swallowed so post_offer() is unaffected"
            )
