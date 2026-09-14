"""Pure per-car advance allocation math.

Single source of truth for how an advance/invoice total is sliced per car so the
advance, storno and final exports all book the SAME rounded EUR per car and
reconcile to zero. These helpers were extracted from ``routes_orders`` so the
invoice state machine can reuse them without importing the routes module (which
imports the state machine — a circular dependency). ``routes_orders`` re-imports
these names, so ``routes_orders._per_car_advance_eur`` etc. still resolve.
"""
from decimal import Decimal, ROUND_HALF_UP

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
