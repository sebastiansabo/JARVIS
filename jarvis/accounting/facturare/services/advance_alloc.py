"""Pure per-car advance allocation math.

Single source of truth for how an advance/invoice total is sliced per car so the
advance, storno and final exports all book the SAME rounded EUR per car and
reconcile to zero. These helpers were extracted from ``routes_orders`` so the
invoice state machine can reuse them without importing the routes module (which
imports the state machine — a circular dependency). ``routes_orders`` re-imports
these names, so ``routes_orders._per_car_advance_eur`` etc. still resolve.
"""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

WHOLE_EUR = Decimal("1")
CENTS = Decimal("0.01")

_PCT_CLOSE_TOL = 0.005  # how near cumulative fraction must be to 1.0 to "close" a car


def _round_half_up(value, quant: Decimal = WHOLE_EUR):
    """Round `value` to `quant` (a whole EUR by default) with halves going up
    (1014.50 -> 1015).

    Python's built-in round() uses banker's rounding (round-half-to-even), so a
    5% advance landing exactly on X.50 with an even X rounds DOWN (1014.50 ->
    1014). Per-car advance amounts must round half up per the accounting spec.

    In "zecimale" mode callers pass `quant=CENTS` so each car keeps its two
    decimals (19997 * 10% = 1999.70 instead of 2000). Whole-EUR rounding returns
    an int (unchanged); cent rounding returns a float.
    """
    q = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return int(q) if quant == WHOLE_EUR else float(q)


def _snap_pct(total_amount, total_selling) -> float:
    """Effective advance percentage, snapped to the nearest whole % when within
    0.5% of one.

    The stored proforma/invoice total is itself a rounded figure (e.g. a 5%
    advance of 8128.20 is stored as 8128.00), so re-deriving each car by slicing
    that total — total_amount * selling / total_selling — loses the exact .50 and
    rounds a 20290 car down to 1014. Snapping the ratio back to a clean 0.05 lets
    each car be computed as selling * pct (1014.50 -> 1015), matching the per-line
    coverage/document-list computation. Non-whole percentages fall through to the
    raw ratio unchanged.
    """
    if not total_selling:
        return 0.0
    raw = total_amount / total_selling
    snapped = round(raw * 100) / 100
    # Never snap a positive advance down to 0% — a real total (e.g. a 0,0999%
    # advance on a 100-car anexa) must keep its raw fraction, else every car
    # renders 0,00 €. Only snap when the clean percent is itself non-zero.
    if snapped != 0 and abs(raw - snapped) < 0.005:
        return snapped
    return raw


def _car_slice_eur(selling, this_fraction, prior_fractions, quant: Decimal = WHOLE_EUR):
    """Amount one invoice books for a single car (cumulative rounding).

    Every non-closing slice rounds its own `selling * fraction` to `quant`. The
    invoice that *closes* the car's coverage — cumulative fraction reaches 1.0 —
    instead books the residual `round(selling) - sum(prior slices)`, so the
    successive slices reconcile to the car's price exactly.

    Without this, a 5% advance and a 95% remainder that both land on X.50 each
    round up and overshoot by 1 EUR: 2288 + 43463 = 45751 instead of
    2288 + 43462 = 45750 (CTR-945 / comanda 352848). Because prior slices are
    themselves rounded to the same `quant`, `sum(prior slices)` telescopes to the
    running total actually invoiced, so the residual reverses exactly what was
    billed. `quant=CENTS` keeps two decimals (zecimale mode); the default whole
    EUR is unchanged.
    """
    if abs(sum(prior_fractions) + this_fraction - 1.0) < _PCT_CLOSE_TOL:
        prior_booked = sum(_round_half_up(selling * f, quant) for f in prior_fractions)
        return _round_half_up(selling, quant) - prior_booked
    return _round_half_up(selling * this_fraction, quant)


def _per_car_advance_eur(inv_total, selling, covered_selling, split_mode, n_lines,
                         prior_fractions=None, quant: Decimal = WHOLE_EUR):
    """Whole-EUR per-car slice of an advance/invoice total.

    Single source of truth for the advance, storno and final exports so all three
    book the SAME rounded EUR per car and reconcile to zero. Proportional splits
    snap the ratio to a clean percent then round half up (matching the invoice
    PDF); equal splits divide and round. Slicing the stored total with 2-decimal
    precision instead (the old storno path) echoed fractional-EUR residues that
    never cleared and mismatched the whole-EUR invoice — e.g. a 5% advance stored
    as 1403.89 must reverse as 1404, not 1403.89.

    `prior_fractions` (the snapped fractions of same-track invoices booked earlier
    on this car) enables the cumulative-rounding residual for the closing slice, so
    a 95% remainder reverses as 43462, not 43463. Omitted (None) keeps the legacy
    independent-round behaviour for callers without sibling context.
    """
    if split_mode == "proportional" and covered_selling:
        return _car_slice_eur(selling, _snap_pct(inv_total, covered_selling),
                              prior_fractions or [], quant)
    return _round_half_up(inv_total / max(n_lines, 1), quant)


def track_prior_booked(covered_ids, prior_invoices, line_prices):
    """``{line_id: EUR already booked}`` for each covered car by the EXISTING
    same-track invoices, computed with the per-car allocator.

    Uses what earlier invoices ACTUALLY booked (not a fraction-implied round), so a
    new advance's closing residual stays consistent with the allocator even when a
    prior invoice stored a pre-canonical total (round(pct × Σprice)) that rounded
    some cars down. The caller passes only the relevant track (PROFORMA accumulates
    with PROFORMA, INVOICE/avans with INVOICE).
    """
    booked = {lid: 0.0 for lid in covered_ids}
    if not prior_invoices:
        return booked
    for per_car in anexa_car_allocations(prior_invoices, line_prices).values():
        for lid, amt in per_car.items():
            if lid in booked:
                booked[lid] += float(amt)
    return booked


def proportional_total(this_fraction, covered_ids, line_prices,
                       prior_booked=None, quant: Decimal = WHOLE_EUR):
    """Self-consistent total for a proportional proforma/advance: the SUM of each
    covered car's cumulative-rounding slice, so the stored total equals Σ of the
    per-car lines the allocator renders — and every car's advance rounds half up.

    A bulk 5% advance on 8 cars of 20290 thus totals 8132 (= 8 × round_half_up(
    1014.50)), not 8128 (= round(5% × 162564)). Storing 8128 forced the allocator
    to round four cars DOWN to 1014 to reconcile to it (CTR-1561). A car whose
    cumulative coverage closes books the residual ``round(price) − prior_booked``
    (what earlier invoices ACTUALLY booked), so advance + rest equals the whole
    price exactly — mirroring ``_allocate_one`` minus the reconcile-to-total.

    `prior_booked`: ``{line_id: EUR already booked on this track}`` (see
    ``track_prior_booked``); omit for a first advance.
    """
    priors = prior_booked or {}
    total = Decimal("0")
    for lid in covered_ids:
        price = float(line_prices.get(lid, 0))
        prior = float(priors.get(lid, 0))
        if price > 0 and abs(prior / price + this_fraction - 1.0) < _PCT_CLOSE_TOL:
            total += Decimal(str(_round_half_up(price, quant))) - Decimal(str(prior))
        else:
            total += Decimal(str(_round_half_up(price * this_fraction, quant)))
    return int(total) if quant == WHOLE_EUR else float(total)


def _hamilton(target: Decimal, weights, quant: Decimal):
    """Apportion `target` across items proportional to `weights`, rounded to
    `quant`, so the rounded slices sum to `target` EXACTLY (largest-remainder).

    Each item gets floor(target*weight/Σweight) to the quant, then the leftover
    whole quants go one each to the largest fractional remainders. Reconciles the
    slices to the document total instead of rounding each car independently
    (2 × 5.613,60 rounded up = 11.228 vs the stored 11.226).
    """
    if not weights:
        return []
    target = Decimal(str(target))
    W = sum(Decimal(str(w)) for w in weights) or Decimal("1")
    ideals = [target * Decimal(str(w)) / W for w in weights]
    floors = [(i / quant).to_integral_value(rounding=ROUND_FLOOR) * quant for i in ideals]
    units = int(((target - sum(floors)) / quant).to_integral_value(rounding=ROUND_HALF_UP))
    alloc = list(floors)
    order = sorted(range(len(weights)), key=lambda i: ideals[i] - floors[i], reverse=True)
    for k in range(max(units, 0)):
        alloc[order[k % len(order)]] += quant
    return [int(a) if quant == WHOLE_EUR else float(a) for a in alloc]


def _allocate_one(inv_total, covered_ids, line_prices, split_mode, quant, prior_booked):
    """Per-car EUR for ONE document, reconciled to round(inv_total).

    A car whose cumulative coverage (its ACTUAL prior bookings on this track plus
    this document's snapped fraction) reaches ~100% books the residual
    ``round(price) − prior_booked`` — the amount that makes advance + rest equal
    the car's whole price, using what earlier invoices ACTUALLY booked (not a
    theoretical ``round(price × fraction)``). The remaining, non-closing cars
    share ``round(inv_total) − Σ(closing residuals)`` via largest-remainder.

    `prior_booked`: {line_id: EUR already booked for this car by earlier
    same-track invoices}.
    """
    quant = Decimal(quant)
    result = {}
    nonclosing = []
    closing_sum = Decimal("0")
    covered_selling = sum(float(line_prices.get(l, 0)) for l in covered_ids) or 1.0
    this_fraction = _snap_pct(float(inv_total), covered_selling) if split_mode == "proportional" else None
    for lid in covered_ids:
        price = float(line_prices.get(lid, 0))
        prior = float(prior_booked.get(lid, 0))
        if this_fraction is not None and price > 0 and \
                abs(prior / price + this_fraction - 1.0) < _PCT_CLOSE_TOL:
            resid = Decimal(str(_round_half_up(price, quant))) - Decimal(str(prior))
            share = int(resid) if quant == WHOLE_EUR else float(resid)
            result[lid] = share
            closing_sum += Decimal(str(share))
        else:
            nonclosing.append((lid, price if split_mode == "proportional" else 1))
    # Non-closing cars share whatever the document total leaves after the closing
    # residuals; clamp at 0 so a (degenerate) over-closed document never hands out
    # negative slices.
    target = max(Decimal(str(_round_half_up(inv_total, quant))) - closing_sum, Decimal("0"))
    for (lid, _), amt in zip(nonclosing, _hamilton(target, [w for _, w in nonclosing], quant)):
        result[lid] = amt
    return result


def _alloc_order_key(inv):
    return (str(inv.get("issued_date") or ""), inv.get("sequence_number") or 0, inv.get("id") or 0)


def anexa_car_allocations(invoices, line_prices):
    """``{invoice_id: {line_id: eur}}`` for every PROFORMA / INVOICE / FINAL of an
    anexa, computed CHRONOLOGICALLY within each independent track.

    Single source of truth for per-car amounts used by the PDF, coverage,
    doc-items, EuroFib and storno-reversal paths. Because each document's cars
    reconcile to its stored total AND a car's closing slice subtracts the ACTUAL
    prior bookings, both invariants hold at once:
      * a bulk 10% proforma's cars sum to its stored total (CTR-790), and
      * a car's 10% + 90% = its whole price (CTR-605, CTR-945).
    PROFORMA, INVOICE and FINAL accumulate on separate tracks (a car's avans
    track is independent of its proforma track), matching the coverage view.
    STORNO is excluded — callers reverse the reversed invoice's allocation.
    """
    import json as _json
    tracks = {}  # invoice_type -> {line_id: cumulative Decimal booked}
    result = {}
    for inv in sorted(invoices, key=_alloc_order_key):
        itype = inv.get("invoice_type")
        if itype not in ("PROFORMA", "INVOICE", "FINAL"):
            continue
        booked = tracks.setdefault(itype, {})
        raw = inv.get("line_ids")
        if isinstance(raw, str):
            raw = _json.loads(raw)
        covered = list(raw) if raw else list(line_prices.keys())
        quant = CENTS if inv.get("round_decimals") else WHOLE_EUR
        shares = _allocate_one(
            float(inv["total_amount_eur"]), covered, line_prices,
            inv.get("split_mode", "equal"), quant,
            {lid: float(booked.get(lid, 0)) for lid in covered})
        result[inv["id"]] = shares
        for lid, amt in shares.items():
            booked[lid] = float(booked.get(lid, 0)) + float(amt)
    return result


def partial_advance_total(proforma_total: Decimal, split_mode: str, quant: Decimal,
                          line_prices: dict, subset_ids, already_ids,
                          already_total: Decimal) -> Decimal:
    """EUR total for an advance invoice that confirms `subset_ids` of a proforma.

    A proforma covering N cars may be confirmed by several advance invoices, each
    over a disjoint subset of its lines. Each car is booked at its canonical
    per-car advance slice (`_per_car_advance_eur`), so a partial invoice matches
    what the PDF/coverage views show. The invoice that *closes* the proforma
    (covers every remaining line) instead books the residual
    `proforma_total - already_total`, so the partial advances reconcile to the
    proforma total exactly regardless of per-car rounding — the same
    closing-slice trick `_car_slice_eur` uses per car, applied per invoice.

    Args:
        proforma_total: the proforma's stored total_amount_eur.
        split_mode: the proforma's split_mode ("equal" | "proportional").
        quant: WHOLE_EUR or CENTS (zecimale) per the proforma's round_decimals.
        line_prices: {line_id: selling_price} for ALL of the proforma's lines.
        subset_ids: the lines being confirmed by this invoice.
        already_ids: the proforma lines confirmed by earlier advance invoices.
        already_total: sum of those earlier invoices' totals.
    """
    all_ids = set(line_prices)
    subset = set(subset_ids)
    covered_selling = sum(line_prices.values())
    n = len(all_ids)
    # Closing invoice: everything the proforma covers is now confirmed.
    if subset | set(already_ids) == all_ids:
        return proforma_total - already_total
    total = Decimal("0")
    for lid in subset:
        slice_eur = _per_car_advance_eur(
            float(proforma_total), float(line_prices[lid]), float(covered_selling),
            split_mode, n, quant=quant)
        total += Decimal(str(slice_eur))
    return total
