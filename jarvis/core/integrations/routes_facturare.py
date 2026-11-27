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
from datetime import date

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

# Only these document types count as an issued fiscal invoice (the summary).
_FISCAL_TYPES = {"FINAL", "INVOICE"}


def _pick_current(documents: list):
    """Pick the live fiscal invoice from a document chain: the latest non-archived
    ``FINAL``, else the latest non-archived ``INVOICE``. ``documents`` are rows
    that actually have an invoice. Returns the chosen row, or None."""
    fiscal = [d for d in documents
              if d.get("invoice_type") in _FISCAL_TYPES and not d.get("archived")]
    if not fiscal:
        return None
    return max(fiscal, key=lambda d: (
        d.get("issued_date") or date.min,
        1 if d.get("invoice_type") == "FINAL" else 0,
        d.get("invoice_number") or 0,
    ))


def _document(row: dict) -> dict:
    return {
        "number": str(row["invoice_number"]),
        "date": row["issued_date"].isoformat() if row.get("issued_date") else None,
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
                "invoice_date": current["issued_date"].isoformat() if current.get("issued_date") else None,
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
