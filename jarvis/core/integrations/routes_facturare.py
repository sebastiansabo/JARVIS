"""JARVIS alpha — facturare (Comenzi Externe) invoice lookup for stock orders.

    POST /api/integrations/business-control/facturare/invoices  {orders:[...]}

Read-only, batch by ``nr_comanda``. Reuses the BUSINESS CONTROL authorization
contract: a browser session cookie or alpha's Bearer access token (bridged to
``current_user`` by app.py's ``_jwt_session_bridge``), gated on the existing
``business_control.access`` permission. facturare is not partitioned by the
company tenant model — the permission grant is the gate.

This module also hosts the pure builders the route composes (``_pick_current``,
``_build_results``), kept free of Flask/DB so they unit-test in isolation.
"""
from flask import jsonify, request
from flask_login import current_user

from core.integrations import integrations_bp
from core.integrations.routes import _has_business_control_access, _audit
from core.utils.api_helpers import error_response, RateLimiter
from core.integrations.facturare_lookup_repository import FacturareLookupRepository

# Defense-in-depth throttle (per authenticated principal), mirroring the
# business-control endpoints' own limiter.
_rate_limiter = RateLimiter()
_RATE_MAX_REQUESTS = 120
_RATE_WINDOW_SECONDS = 60
_MAX_ORDERS = 1000

_repo = FacturareLookupRepository()

# Only these document types count as an issued fiscal invoice (the summary).
_FISCAL_TYPES = {"FINAL", "INVOICE"}


def _iso(value):
    """Normalize a date-ish value to an ISO ``YYYY-MM-DD`` string. The repo returns
    dates already ISO-stringified (BaseRepository.dict_from_row), but accept real
    ``date`` objects too so the builders are robust to either caller."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _pick_current(documents: list):
    """Pick the live fiscal invoice from a document chain: the latest non-archived
    ``FINAL``, else the latest non-archived ``INVOICE``. ``documents`` are rows
    that actually have an invoice. Returns the chosen row, or None."""
    fiscal = [d for d in documents
              if d.get("invoice_type") in _FISCAL_TYPES and not d.get("archived")]
    if not fiscal:
        return None
    # Sort in the string domain — ISO dates sort chronologically and "" (missing
    # date) sorts before any real date, so date/None/str mix never raises.
    return max(fiscal, key=lambda d: (
        _iso(d.get("issued_date")) or "",
        1 if d.get("invoice_type") == "FINAL" else 0,
        d.get("invoice_number") or 0,
    ))


def _document(row: dict) -> dict:
    return {
        "number": str(row["invoice_number"]),
        "date": _iso(row.get("issued_date")),
        "type": row.get("invoice_type"),
        "archived": bool(row.get("archived")),
    }


def _build_results(order_inputs: list, rows: list):
    """Group repo rows into the JSON-ready response. Input orders are trimmed,
    deduped, and kept in order. Returns ``(results, not_found)`` where not_found
    are the trimmed input orders with no matching anexa line at all."""
    seen = set()
    orders = []
    for raw in order_inputs:
        if not raw:
            continue
        o = raw.strip()
        if o and o not in seen:
            seen.add(o)
            orders.append(o)

    groups = {}
    for r in rows:
        groups.setdefault(r["nr_comanda"], []).append(r)

    results, not_found = [], []
    for o in orders:
        grp = groups.get(o)
        if not grp:
            not_found.append(o)
            continue
        vin = next((g.get("vin") for g in grp if g.get("vin")), None)
        item = next((g.get("model") for g in grp if g.get("model")), None)
        doc_rows = [g for g in grp if g.get("invoice_number") is not None]
        documents = [_document(g) for g in doc_rows]
        current = _pick_current(doc_rows)
        if current:
            results.append({
                "nr_comanda": o, "vin": vin, "has_invoice": True,
                "invoice_number": str(current["invoice_number"]),
                "invoice_date": _iso(current.get("issued_date")),
                "invoice_type": current.get("invoice_type"),
                "item": item,
                "amount_eur": float(current["total_amount_eur"]) if current.get("total_amount_eur") is not None else None,
                "amount_ron": float(current["total_amount_ron"]) if current.get("total_amount_ron") is not None else None,
                "currency": current.get("currency"),
                "documents": documents,
            })
        else:
            results.append({
                "nr_comanda": o, "vin": vin, "has_invoice": False,
                "invoice_number": None, "invoice_date": None, "invoice_type": None,
                "item": item, "amount_eur": None, "amount_ron": None, "currency": None,
                "documents": documents,
            })
    return results, not_found


# ── Route ──────────────────────────────────────────────────────────────────────

@integrations_bp.route('/api/integrations/business-control/facturare/invoices', methods=['POST'])
def facturare_invoices_lookup():
    """Batch facturare invoice lookup by nr_comanda. Same auth/permission gate as
    the business-control endpoints (session cookie or alpha's Bearer token +
    ``business_control.access``)."""
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    allowed, retry_after = _rate_limiter.is_allowed(
        f'bc:facturare:{current_user.id}',
        max_requests=_RATE_MAX_REQUESTS, window_seconds=_RATE_WINDOW_SECONDS)
    if not allowed:
        resp, code = error_response('Too many requests', 429)
        resp.headers['Retry-After'] = str(retry_after)
        return resp, code

    if not getattr(current_user, 'is_active', False) or not _has_business_control_access(current_user):
        return error_response('Permission denied', 403)

    data = request.get_json(silent=True) or {}
    orders = data.get('orders')
    if not isinstance(orders, list) or not orders:
        return error_response('orders must be a non-empty list', 400)
    if len(orders) > _MAX_ORDERS:
        return error_response(f'orders exceeds the {_MAX_ORDERS}-item limit', 400)
    if not all(isinstance(o, str) for o in orders):
        return error_response('orders must be a list of strings', 400)

    rows = _repo.by_order_numbers(orders)
    results, not_found = _build_results(orders, rows)
    _audit('business_control.facturare_lookup', current_user, f'{len(orders)} orders', True)
    return jsonify({'success': True, 'results': results, 'not_found': not_found})
