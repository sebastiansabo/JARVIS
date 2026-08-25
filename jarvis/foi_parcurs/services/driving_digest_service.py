"""Weekly Driving Digest — AI-narrated weekly summary of Foi de Parcurs activity.

One report per Company-Brand (to company managers) + a cumulative Board report,
emailed Monday morning for the previous Mon-Sun. Reuses the Rapoarte aggregates
(report_bundle/report_fleet); LLM narrative via ai_agent; no new report SQL.
"""
import json
import logging
import os
from datetime import datetime as _dt, timedelta
from html import escape
from zoneinfo import ZoneInfo

from foi_parcurs.repositories import FoiParcursRepository, FPVehicleRepository
from core.organization.repositories.company_repository import CompanyRepository
from core.auth.repositories.user_repository import UserRepository
from core.services.notification_service import send_email as _send_email, is_smtp_configured as _smtp_ok
from core.notifications.notify import notify_users as _notify_users

try:
    from ai_agent.services.llm_client import ask as _llm_ask
except Exception:  # pragma: no cover - llm optional at import time
    _llm_ask = None

logger = logging.getLogger('jarvis.foi_parcurs.driving_digest')

_fp_repo = FoiParcursRepository()
_vehicle_repo = FPVehicleRepository()
_company_repo = CompanyRepository()
_user_repo = UserRepository()

_TOP = 5
_DEFAULT_MODEL = 'claude-sonnet-4-6'
_TZ = ZoneInfo('Europe/Bucharest')

_SYSTEM = (
    "Ești JARVIS, asistentul intern AUTOWORLD. Scrie un rezumat săptămânal concis "
    "(max ~1200 caractere) despre activitatea de driving pentru {scope}. Acoperă: "
    "performanță & clasament (consilieri/mașini), alerte & anomalii (retururi ratate, "
    "mașini nefolosite), mix client vs. intern & firmă vs. persoană, ocupare & distanțe. "
    "Ton profesional, la obiect, în limba română. Text simplu, fără markdown."
)


def _week_range(now):
    """(date_from, date_to) 'YYYY-MM-DD' for the previous Mon..Sun (inclusive).

    `now` is expected to already be Europe/Bucharest local time (generate_and_send
    supplies a tz-aware Bucharest `now` by default when the caller omits one).
    """
    # Monday of the current week, then step back 7 days → previous Monday.
    this_monday = (now - timedelta(days=now.weekday())).date()
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.isoformat(), last_sunday.isoformat()


def _enumerate_company_brands(companies):
    """Flatten companies → (company_id, company_name, brand) per active brand."""
    pairs = []
    for c in companies:
        for b in (c.get('brands_list') or []):
            brand = (b.get('brand') or '').strip()
            if brand:
                pairs.append((c['id'], c.get('company') or f"Companie {c['id']}", brand))
    return pairs


def _collect(company_id, brand, date_from, date_to):
    """Company-Brand scoped metrics: merges report_bundle + report_fleet."""
    bundle = _fp_repo.report_bundle(company_id=company_id, date_from=date_from, date_to=date_to,
                                    document_type='sales', top=_TOP, brand=brand)
    fleet = _vehicle_repo.report_fleet(company_id=company_id, document_type='sales',
                                       odo_order='high', top=_TOP, brand=brand)
    return {'scope': 'company', **bundle, **fleet}


def _collect_board(date_from, date_to):
    """Group-wide metrics (no company/brand scope) for the Board report."""
    bundle = _fp_repo.report_bundle(company_id=None, date_from=date_from, date_to=date_to,
                                    document_type='sales', top=_TOP, brand=None)
    fleet = _vehicle_repo.report_fleet(company_id=None, document_type='sales',
                                       odo_order='high', top=_TOP, brand=None)
    return {'scope': 'group', **bundle, **fleet}


def _narrative(metrics, scope_label):
    """AI-written Romanian summary; falls back to a deterministic template on
    any error or empty response (no API key on staging, provider hiccup, etc.).

    The model is pinned to `claude-sonnet-4-6` (NOT the DB-driven
    ModelConfigRepository default): the provider always sends `temperature`, and
    a sonnet-5 model 400s on that parameter.
    """
    if _llm_ask:
        try:
            txt = _llm_ask(
                f"Generează rezumatul din aceste metrici:\n{json.dumps(metrics, default=str)}",
                system=_SYSTEM.format(scope=scope_label),
                model=_DEFAULT_MODEL,
            )
            if txt and txt.strip():
                return txt.strip()
        except Exception:
            logger.warning('driving digest LLM failed for %s; using fallback', scope_label, exc_info=True)
    return _narrative_plain(metrics, scope_label)


def _narrative_plain(metrics, scope_label):
    k = metrics.get('kpis') or {}
    return (f"{scope_label}: {k.get('total_sessions', 0)} sesiuni, "
            f"{k.get('total_km', 0)} km, rată finalizare {k.get('completion_rate', 0)}%.")


def _render_section(title, metrics, narrative):
    k = metrics.get('kpis') or {}
    return (
        f'<section style="margin:0 0 24px;padding:16px;border:1px solid #e1e0d9;border-radius:10px">'
        f'<h2 style="margin:0 0 8px;font:600 16px system-ui">{escape(title)}</h2>'
        f'<p style="margin:0 0 12px;color:#52514e;white-space:pre-line">{escape(narrative)}</p>'
        f'<table style="border-collapse:collapse;font:13px system-ui">'
        f'<tr><td style="padding:2px 12px 2px 0;color:#898781">Sesiuni</td><td><b>{k.get("total_sessions", 0)}</b></td></tr>'
        f'<tr><td style="padding:2px 12px 2px 0;color:#898781">Km parcurși</td><td><b>{k.get("total_km", 0)}</b></td></tr>'
        f'<tr><td style="padding:2px 12px 2px 0;color:#898781">Rată finalizare</td><td><b>{k.get("completion_rate", 0)}%</b></td></tr>'
        f'</table></section>'
    )


def _render_email(sections, week_label):
    body = ''.join(sections)
    return (
        f'<!doctype html><html><body style="margin:0;padding:16px;background:#f4f4f2">'
        f'<h1 style="font:680 20px system-ui;margin:0 0 4px">Digest Driving săptămânal</h1>'
        f'<p style="color:#898781;font:13px system-ui;margin:0 0 20px">Săptămâna {escape(week_label)}</p>'
        f'{body}</body></html>'
    )


def _company_recipients(company_id):
    """(emails, user_ids) for a company's managers, falling back to
    companies.alert_email when no responsable has an email on file.

    `CompanyRepository.get_responsables(company_id)` returns rows shaped
    `{user_id, user_name}` — no email — so the responsables' addresses are
    resolved through the users table via an id → email map from
    `_user_repo.get_all()`. Only responsables that have an email are kept.
    """
    resp = _company_repo.get_responsables(company_id) or []
    resp_ids = [r['user_id'] for r in resp if r.get('user_id')]
    if resp_ids:
        email_by_id = {u['id']: u.get('email') for u in (_user_repo.get_all() or [])}
        emails, ids = [], []
        for uid in resp_ids:
            email = email_by_id.get(uid)
            if email:
                emails.append(email)
                ids.append(uid)
        if emails:
            return emails, ids
    # fallback: the company's alert_email (no in-app recipients then)
    c = _company_repo.get(company_id) or {}
    if c.get('alert_email'):
        return [c['alert_email']], []
    return [], []


def _board_recipients():
    """(emails, user_ids) for users with role_name == 'board' (case-insensitive),
    matching foi_parcurs/routes/reports.py's _GROUP_ROLES membership."""
    users = _user_repo.get_all() or []
    board = [u for u in users if (u.get('role_name') or '').lower() == 'board']
    return [u['email'] for u in board if u.get('email')], [u['id'] for u in board if u.get('id')]


def _all_companies():
    return _company_repo.get_all_with_vat_and_brands() or []


def _settings_enabled():
    """Reads the `weekly_driving_digest_enabled` notification setting (default
    false). Any error (missing table on a stale DB, etc.) is treated as disabled."""
    try:
        from core.notifications.repositories import NotificationRepository
        s = NotificationRepository().get_settings() or {}
        return str(s.get('weekly_driving_digest_enabled', 'false')).lower() == 'true'
    except Exception:
        return False


def _is_prod():
    try:
        from core.config import is_production
        return bool(is_production())
    except Exception:
        return os.environ.get('FLASK_ENV') == 'production'


def _fmt_week(date_from, date_to):
    return f"{date_from[8:10]}.{date_from[5:7]}–{date_to[8:10]}.{date_to[5:7]}"


def _send_report(subject, html, emails, user_ids, title, message):
    """Email one report HTML to every address + fire an in-app note to user_ids.
    Returns the count of emails that were actually accepted. A failed send is
    logged (with the error string) rather than silently swallowed."""
    sent = 0
    for addr in emails:
        ok, err = _send_email(to_email=addr, subject=subject, html_body=html, skip_global_cc=True)
        if ok:
            sent += 1
        else:
            logger.warning('driving digest email to %s failed: %s', addr, err)
    if user_ids:
        _notify_users(user_ids=user_ids, title=title, message=message,
                      link='/app/foi-parcurs', type='info')
    return sent


def generate_and_send(now=None):
    """Build and send the weekly driving digest: one email per Company-Brand
    to that company's managers, plus a cumulative report to the Board.

    No-ops (returns {'sent': 0, 'skipped': reason}) unless the notification
    setting is enabled AND the environment is production AND SMTP is
    configured — in that exact gate order, so staging never emails.
    """
    if not _settings_enabled():
        return {'sent': 0, 'skipped': 'disabled'}
    if not _is_prod():
        return {'sent': 0, 'skipped': 'not_prod'}
    if not _smtp_ok():
        return {'sent': 0, 'skipped': 'no_smtp'}

    now = now or _dt.now(_TZ)
    date_from, date_to = _week_range(now)
    week_label = _fmt_week(date_from, date_to)
    sent = 0

    # per Company-Brand → company managers. Each company is isolated: one
    # company's failure (collect/render/send) must not abort the rest, nor the
    # Board report that runs after this loop.
    for company_id, company_name, brand in _enumerate_company_brands(_all_companies()):
        try:
            metrics = _collect(company_id, brand, date_from, date_to)
            scope = f"{company_name} · {brand}"
            html = _render_email([_render_section(scope, metrics, _narrative(metrics, scope))], week_label)
            emails, user_ids = _company_recipients(company_id)
            sent += _send_report(
                f"Digest Driving — {scope} — săptămâna {week_label}", html, emails, user_ids,
                'Digest Driving săptămânal', f'{scope}: raportul săptămânal este disponibil.')
        except Exception:
            logger.warning('driving digest failed for company %s brand %s; skipping',
                           company_id, brand, exc_info=True)
            continue

    # cumulative → Board
    board_metrics = _collect_board(date_from, date_to)
    board_html = _render_email(
        [_render_section('Grup AUTOWORLD', board_metrics, _narrative(board_metrics, 'Grup AUTOWORLD'))],
        week_label)
    b_emails, b_ids = _board_recipients()
    sent += _send_report(
        f"Digest Driving — Grup AUTOWORLD — săptămâna {week_label}", board_html, b_emails, b_ids,
        'Digest Driving săptămânal (Grup)', 'Raportul săptămânal de grup este disponibil.')

    logger.info('weekly driving digest sent: %s emails (week %s)', sent, week_label)
    return {'sent': sent, 'skipped': None}
