"""Weekly Driving Digest — AI-narrated weekly summary of Foi de Parcurs activity.

One report per Company-Brand (to company managers) + a cumulative Board report,
emailed Monday morning for the previous Mon-Sun. Reuses the Rapoarte aggregates
(report_bundle/report_fleet); LLM narrative via ai_agent; no new report SQL.
"""
import json
import logging
from datetime import timedelta
from html import escape

from foi_parcurs.repositories import FoiParcursRepository, FPVehicleRepository

try:
    from ai_agent.services.llm_client import ask as _llm_ask
except Exception:  # pragma: no cover - llm optional at import time
    _llm_ask = None

logger = logging.getLogger('jarvis.foi_parcurs.driving_digest')

_fp_repo = FoiParcursRepository()
_vehicle_repo = FPVehicleRepository()

_TOP = 5
_DEFAULT_MODEL = 'claude-sonnet-4-6'

_SYSTEM = (
    "Ești JARVIS, asistentul intern AUTOWORLD. Scrie un rezumat săptămânal concis "
    "(max ~1200 caractere) despre activitatea de driving pentru {scope}. Acoperă: "
    "performanță & clasament (consilieri/mașini), alerte & anomalii (retururi ratate, "
    "mașini nefolosite), mix client vs. intern & firmă vs. persoană, ocupare & distanțe. "
    "Ton profesional, la obiect, în limba română. Text simplu, fără markdown."
)


def _week_range(now):
    """(date_from, date_to) 'YYYY-MM-DD' for the previous Mon..Sun (inclusive)."""
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


def _model_name():
    try:
        from ai_agent.repositories import ModelConfigRepository
        cfg = ModelConfigRepository().get_default()
        if cfg and getattr(cfg, 'model_name', None):
            return cfg.model_name
    except Exception:
        pass
    return _DEFAULT_MODEL


def _narrative(metrics, scope_label):
    """AI-written Romanian summary; falls back to a deterministic template on
    any error or empty response (no API key on staging, provider hiccup, etc.)."""
    if _llm_ask:
        try:
            txt = _llm_ask(
                f"Generează rezumatul din aceste metrici:\n{json.dumps(metrics, default=str)}",
                system=_SYSTEM.format(scope=scope_label),
                model=_model_name(),
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
