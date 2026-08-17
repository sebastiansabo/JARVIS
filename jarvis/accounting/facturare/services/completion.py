"""Derived completeness for Comenzi anexas/contracts.

An anexa is "fully invoiced" when every line's net invoiced amount
(INVOICE + FINAL − STORNO, proportional per covered line) reaches its
selling price, and no proforma is left unpaired. PROFORMA never counts —
advances are not revenue. A contract is complete when it has at least one
anexa and all of them are complete.
"""
import json
from decimal import Decimal, ROUND_HALF_UP

_WHOLE = Decimal("1")
# Per-line tolerance: proportional shares round to whole EUR, so a fully
# invoiced line can land up to ~€0.50 under its cents-precise price. €1
# absorbs that without ever passing a genuinely under-invoiced line
# (amounts are thousands of EUR).
_TOLERANCE = Decimal("1")


def _covered_line_ids(inv, all_ids):
    raw = inv.get("line_ids")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return set(raw) if raw else set(all_ids)


def net_invoiced_per_line(repo, anexa_id):
    """Return (net, price): {line_id: Decimal} maps of net invoiced and selling price."""
    lines = repo.get_lines_by_anexa(anexa_id)
    all_ids = [l["id"] for l in lines]
    price = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in lines}
    net = {lid: Decimal("0") for lid in all_ids}
    for inv in repo.get_invoices_by_anexa(anexa_id):
        if inv["invoice_type"] not in ("INVOICE", "FINAL", "STORNO"):
            continue
        amt = Decimal(str(inv["total_amount_eur"]))  # STORNO is stored negative
        covered = _covered_line_ids(inv, all_ids)
        covered_total = sum((price.get(lid, Decimal("0")) for lid in covered), Decimal("0"))
        if not covered_total:
            continue
        for lid in covered:
            share = (price.get(lid, Decimal("0")) / covered_total * amt).quantize(
                _WHOLE, rounding=ROUND_HALF_UP)
            net[lid] = net.get(lid, Decimal("0")) + share
    return net, price


def _has_unpaired_proforma(repo, anexa_id):
    invs = repo.get_invoices_by_anexa(anexa_id)
    proforma_seqs = {i["sequence_number"] for i in invs if i["invoice_type"] == "PROFORMA"}
    invoice_seqs = {i["sequence_number"] for i in invs if i["invoice_type"] == "INVOICE"}
    return bool(proforma_seqs - invoice_seqs)


def is_anexa_complete(repo, anexa_id):
    lines = repo.get_lines_by_anexa(anexa_id)
    if not lines:
        return False
    if _has_unpaired_proforma(repo, anexa_id):
        return False
    net, price = net_invoiced_per_line(repo, anexa_id)
    return all(net.get(lid, Decimal("0")) >= p - _TOLERANCE for lid, p in price.items())


def is_contract_complete(repo, contract_id):
    anexas = repo.list_anexas_by_contract(contract_id)
    if not anexas:
        return False
    return all(is_anexa_complete(repo, a["id"]) for a in anexas)
