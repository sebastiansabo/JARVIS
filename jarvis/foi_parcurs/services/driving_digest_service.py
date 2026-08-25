"""Weekly Driving Digest — AI-narrated weekly summary of Foi de Parcurs activity.

One report per Company-Brand (to company managers) + a cumulative Board report,
emailed Monday morning for the previous Mon-Sun. Reuses the Rapoarte aggregates
(report_bundle/report_fleet); LLM narrative via ai_agent; no new report SQL.
"""
import json
import logging
from datetime import timedelta

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
