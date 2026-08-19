"""Derived completeness for Comenzi anexas/contracts.

An anexa is complete (archivable) only when every car has been *finally
invoiced*: each line must be covered by a FINAL invoice (factura finală) AND
its net invoiced amount (INVOICE + FINAL − STORNO, proportional per covered
line) must reach its selling price, with no proforma left unpaired. A full
advance invoice (invoice_type INVOICE = factura de avans) reaches the selling
price on its own but does NOT complete the anexa — revenue is booked only at
final invoicing. PROFORMA never counts. A contract is complete when it has at
least one anexa and all of them are complete.
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


def _final_covered_line_ids(repo, anexa_id):
    """Set of line ids covered by at least one FINAL invoice.

    A line is "finally invoiced" once a factura finală (invoice_type FINAL)
    covers it — either explicitly via line_ids or implicitly (line_ids empty =
    whole anexa). This is the gate that stops a full advance (INVOICE) from
    completing — and archiving — an anexa before its final invoice exists.
    """
    lines = repo.get_lines_by_anexa(anexa_id)
    all_ids = [l["id"] for l in lines]
    covered = set()
    for inv in repo.get_invoices_by_anexa(anexa_id):
        if inv["invoice_type"] != "FINAL":
            continue
        covered |= _covered_line_ids(inv, all_ids)
    return covered


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
    # Every car must be finally invoiced — a full advance alone must not
    # complete (and archive) the anexa before its factura finală exists.
    final_covered = _final_covered_line_ids(repo, anexa_id)
    if any(l["id"] not in final_covered for l in lines):
        return False
    net, price = net_invoiced_per_line(repo, anexa_id)
    return all(net.get(lid, Decimal("0")) >= p - _TOLERANCE for lid, p in price.items())


def is_contract_complete(repo, contract_id):
    anexas = repo.list_anexas_by_contract(contract_id)
    if not anexas:
        return False
    return all(is_anexa_complete(repo, a["id"]) for a in anexas)
