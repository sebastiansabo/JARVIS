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
    "Ești JARVIS, analistul AUTOWORLD. Scrie un rezumat săptămânal FOARTE CONCIS despre "
    "activitatea de driving pentru {scope}, în limba română — maxim 3 propoziții scurte "
    "(sub ~400 caractere în total). Menționează: cel mai activ consilier sau mașină, o "
    "singură alertă importantă (retururi ratate / mașini nefolosite / finalizare scăzută) "
    "și o recomandare scurtă. Doar esențialul, ton profesional, text simplu fără markdown."
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


_STATUS_RO = {'complete': 'Finalizate', 'planned': 'Planificate', 'driving': 'În desfășurare',
              'late': 'Întârziate', 'incomplete': 'Neîncheiate', 'missed': 'Ratate', 'pending': 'În așteptare'}
_TYPE_RO = {'test_drive': 'Test drive', 'comodat': 'Comodat', 'service': 'Curtoazie', 'internal': 'Intern'}
_SEG_RO = {'client': 'Cu client', 'internal': 'Intern'}
_CT_RO = {'company': 'Firmă', 'person': 'Persoană fizică'}


def _nf(n):
    try:
        return f"{int(round(float(n or 0))):,}".replace(',', '.')
    except (TypeError, ValueError):
        return str(n)


def _kpi_grid(k):
    tiles = [('Sesiuni', _nf(k.get('total_sessions', 0))), ('Km parcurși', _nf(k.get('total_km', 0))),
             ('Mașini utilizate', _nf(k.get('cars_used', 0))), ('Km / sesiune', _nf(k.get('avg_km_per_session', 0))),
             ('Test drive-uri', _nf(k.get('test_drives', 0))), ('Rată finalizare', f"{k.get('completion_rate', 0)}%")]
    td = ('<td style="padding:8px 12px;border:1px solid #ecebe6;background:#fafafa;border-radius:8px;width:33%">'
          '<div style="font:11px system-ui;color:#898781;text-transform:uppercase;letter-spacing:.03em">{l}</div>'
          '<div style="font:700 18px system-ui;color:#0b0b0b">{v}</div></td>')
    cells = [td.format(l=escape(l), v=v) for l, v in tiles]
    r1, r2 = '<tr>' + ''.join(cells[:3]) + '</tr>', '<tr>' + ''.join(cells[3:]) + '</tr>'
    return f'<table style="border-collapse:separate;border-spacing:6px;width:100%;margin:0 0 14px">{r1}{r2}</table>'


def _mini_table(title, headers, rows):
    if not rows:
        return ''
    th = ''.join(
        f'<th style="text-align:{"right" if i else "left"};padding:4px 8px;font:600 11px system-ui;'
        f'color:#898781;text-transform:uppercase;border-bottom:1px solid #e1e0d9">{escape(h)}</th>'
        for i, h in enumerate(headers))
    body = ''
    for r in rows:
        tds = ''.join(
            f'<td style="text-align:{"right" if i else "left"};padding:5px 8px;font:13px system-ui;'
            f'border-bottom:1px solid #f0efec">{escape(str(c))}</td>' for i, c in enumerate(r))
        body += f'<tr>{tds}</tr>'
    return (f'<div style="margin:0 0 12px"><div style="font:600 13px system-ui;margin:0 0 4px">{escape(title)}</div>'
            f'<table style="border-collapse:collapse;width:100%"><tr>{th}</tr>{body}</table></div>')


def _chips(title, items):
    items = [(l, c) for l, c in items if c]
    if not items:
        return ''
    chips = ' '.join(
        f'<span style="display:inline-block;padding:2px 9px;margin:0 4px 4px 0;border-radius:999px;'
        f'background:#eef2fb;font:12px system-ui;color:#33475b">{escape(str(l))}: <b>{_nf(c)}</b></span>'
        for l, c in items)
    return f'<div style="margin:0 0 12px"><span style="font:600 13px system-ui">{escape(title)}:</span> {chips}</div>'


def _render_section(title, metrics, narrative):
    """Rich per-scope section — a CONCISE narrative on top, then ALL report blocks
    as compact tables/chips (KPI grid, leaderboards, status/type/mix, brand/fuel,
    top clients, and per-company for the Board scope)."""
    k = metrics.get('kpis') or {}
    body = [f'<h2 style="margin:0 0 10px;font:700 17px system-ui;color:#0b0b0b">{escape(title)}</h2>']
    if narrative:
        body.append(
            f'<div style="margin:0 0 14px;padding:12px 14px;background:#f4f6fb;border-left:3px solid #2a78d6;'
            f'border-radius:6px;font:14px/1.5 system-ui;color:#33475b;white-space:pre-line">{escape(narrative)}</div>')
    body.append(_kpi_grid(k))
    # per-company leaderboard (Board scope only)
    body.append(_mini_table('Performanță pe companii', ['Companie', 'Sesiuni', 'Km'],
                            [[c.get('company', '—'), _nf(c.get('sessions', 0)), _nf(c.get('km', 0))]
                             for c in (metrics.get('top_companies') or [])[:8]]))
    body.append(_mini_table('Top consilieri', ['Consilier', 'Sesiuni', 'Km', 'Finalizare'],
                            [[a.get('advisor', '—'), _nf(a.get('sessions', 0)), _nf(a.get('km', 0)), f"{a.get('completion_rate', 0)}%"]
                             for a in (metrics.get('top_advisors') or [])[:5]]))
    body.append(_mini_table('Top mașini (după sesiuni)', ['Mașină', 'Sesiuni', 'Zile', 'Km'],
                            [[f"{u.get('model', '—')} · {u.get('registration_number', '')}".strip(' ·'),
                              _nf(u.get('sessions', 0)), _nf(u.get('days_used', 0)), _nf(u.get('km', 0))]
                             for u in (metrics.get('utilization') or [])[:5]]))
    body.append(_mini_table('Top mașini (după km bord)', ['Mașină', 'Km bord'],
                            [[f"{v.get('model', '—')} · {v.get('registration_number', '')}".strip(' ·'), _nf(v.get('odometer_km', 0))]
                             for v in (metrics.get('top_odometer') or [])[:5]]))
    body.append(_mini_table('Top clienți', ['Client', 'Tip', 'Sesiuni', 'Km'],
                            [[c.get('client', '—'), _CT_RO.get(c.get('client_type'), c.get('client_type', '')),
                              _nf(c.get('sessions', 0)), _nf(c.get('km', 0))]
                             for c in (metrics.get('top_clients') or [])[:5]]))
    body.append(_chips('Status', [(_STATUS_RO.get(s.get('status'), s.get('status', '—')), s.get('count', 0)) for s in (metrics.get('by_status') or [])]))
    body.append(_chips('Tip sesiune', [(_TYPE_RO.get(t.get('type'), t.get('type', '—')), t.get('count', 0)) for t in (metrics.get('by_type') or [])]))
    body.append(_chips('Client vs. intern', [(_SEG_RO.get(s.get('segment'), s.get('segment', '—')), s.get('count', 0)) for s in (metrics.get('client_vs_internal') or [])]))
    body.append(_chips('Tip client', [(_CT_RO.get(c.get('client_type'), c.get('client_type', '—')), c.get('count', 0)) for c in (metrics.get('client_types') or [])]))
    body.append(_chips('Sesiuni pe marcă', [(b.get('brand', '—'), b.get('count', 0)) for b in (metrics.get('by_brand') or [])]))
    body.append(_chips('Parc după combustibil', [(f.get('fuel_type', '—'), f.get('count', 0)) for f in (metrics.get('fuel_composition') or [])]))
    body.append(_mini_table('Distanță pe marcă (km)', ['Marcă', 'Km'],
                            [[d.get('brand', '—'), _nf(d.get('km', 0))] for d in (metrics.get('distance_by_brand') or [])[:8]]))
    return (f'<section style="margin:0 0 26px;padding:18px;border:1px solid #e1e0d9;border-radius:12px;'
            f'background:#fff">{"".join(body)}</section>')


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


def _board_recipient_override():
    """Explicit Board addresses from the `weekly_driving_digest_board_recipients`
    notification setting (comma/semicolon-separated), or [] when unset.

    Lets the Board report be pointed at a fixed distribution address
    (e.g. board@autoworld.ro) with no JARVIS user account or 'board' role. The
    isinstance-str guard keeps a mocked/malformed settings value (non-string)
    from being parsed into a bogus address."""
    try:
        from core.notifications.repositories import NotificationRepository
        raw = (NotificationRepository().get_settings() or {}).get('weekly_driving_digest_board_recipients', '')
    except Exception:
        return []
    if not isinstance(raw, str):
        return []
    return [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]


def _board_recipients():
    """(emails, user_ids) for the Board report.

    A `weekly_driving_digest_board_recipients` setting (comma/semicolon-separated
    addresses) takes precedence when set — the report goes to those addresses with
    no in-app recipients (they need not be JARVIS users). Otherwise falls back to
    users whose role_name == 'board' (case-insensitive), matching
    foi_parcurs/routes/reports.py's _GROUP_ROLES membership."""
    override = _board_recipient_override()
    if override:
        return override, []
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
    """True only on the production deployment. The DO services carry no
    FLASK_ENV, so prod is detected by the prod DB host in DATABASE_URL
    (`jarvis-main-do-user`); FLASK_ENV=='production' is kept as a secondary
    signal for any environment that does set it. This is defense-in-depth — the
    per-DB `weekly_driving_digest_enabled` flag is the primary send gate."""
    db = os.environ.get('DATABASE_URL', '')
    return 'jarvis-main-do-user' in db or os.environ.get('FLASK_ENV') == 'production'


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
