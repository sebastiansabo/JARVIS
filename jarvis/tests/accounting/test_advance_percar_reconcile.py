"""Per-car advance slices must reconcile to the document's stored total.

Regression for CTR-790 / AW Next proforma No:7 (client Staiger Dich): a 2-car
proportional advance whose proforma was collected at 11.226 € re-rendered as
11.228 € because each car's 56.136 × 10% = 5.613,60 was independently rounded
half-up to 5.614 (2 × 5.614 = 11.228), overshooting the stored/collected total
by 2 €.

`allocate_car_advances` distributes the document's stored total across its cars
so the slices sum EXACTLY to it (5.613 + 5.613 = 11.226), while a car that
*closes* its cumulative coverage still books the residual so advance + rest
reconcile to the car's price (the CTR-945 invariant must survive).
"""
import os
import sys
from decimal import Decimal

import pytest

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from accounting.facturare.services.advance_alloc import (  # noqa: E402
    allocate_car_advances, WHOLE_EUR, CENTS,
)


def _line(id_, price):
    return {"id": id_, "selling_price_eur": price}


# ── CTR-790: the reported bug ─────────────────────────────────────────────────

def test_ctr790_proportional_whole_reconciles_to_stored_total():
    # Proforma 992: 2 × 56.136 €, stored total 11.226 €, proportional, whole EUR.
    lines = [_line(1044, 56136.00), _line(1045, 56136.00)]
    shares = allocate_car_advances(11226.00, lines, "proportional", WHOLE_EUR)
    assert shares[1044] == 5613
    assert shares[1045] == 5613
    assert sum(shares.values()) == 11226  # was 11228


def test_ctr790_does_not_overshoot():
    lines = [_line(1044, 56136.00), _line(1045, 56136.00)]
    shares = allocate_car_advances(11226.00, lines, "proportional", WHOLE_EUR)
    assert sum(shares.values()) != 11228


# ── CTR-945 invariant: closing car books the residual (advance + rest = price) ─

def test_closing_car_books_residual_not_independent_round():
    # 95% remainder on a 45.750 € car that already had a 5% advance: must book
    # 45750 - 2288 = 43462, NOT round_half_up(45750 * 0.95) = 43463.
    lines = [_line(10, 45750.00)]
    shares = allocate_car_advances(43462.50, lines, "proportional", WHOLE_EUR,
                                   priors_by_line={10: [0.05]})
    assert shares[10] == 43462


def test_advance_plus_rest_reconcile_to_selling():
    lines = [_line(10, 45750.00)]
    advance = allocate_car_advances(2287.50, lines, "proportional", WHOLE_EUR)[10]
    rest = allocate_car_advances(43462.50, lines, "proportional", WHOLE_EUR,
                                 priors_by_line={10: [0.05]})[10]
    assert advance == 2288
    assert advance + rest == 45750


# ── CTR-1646: zecimale keeps cents; whole EUR now reconciles (no overshoot) ────

def test_zecimale_keeps_cents_and_reconciles():
    lines = [_line(i, 19997.00) for i in range(100)]
    shares = allocate_car_advances(199970.00, lines, "proportional", CENTS)
    assert all(v == pytest.approx(1999.70) for v in shares.values())
    assert sum(shares.values()) == pytest.approx(199970.00)


def test_whole_eur_overshoot_now_reconciles_to_total():
    # 100 × 19.997 × 10% = 1.999,70 each: independently rounding up to 2.000
    # overshot by 30 €. Must now sum to the stored 199.970 €.
    lines = [_line(i, 19997.00) for i in range(100)]
    shares = allocate_car_advances(199970.00, lines, "proportional", WHOLE_EUR)
    assert sum(shares.values()) == 199970  # was 200000
    assert all(v in (1999, 2000) for v in shares.values())


# ── equal split distributes the total, not a per-car round-up ─────────────────

def test_equal_split_distributes_total():
    lines = [_line(i, 19997.00) for i in range(100)]
    shares = allocate_car_advances(199900.00, lines, "equal", WHOLE_EUR)
    assert sum(shares.values()) == 199900
    assert all(v == 1999 for v in shares.values())


# ── snap-to-zero guard: a tiny advance must not zero every car ────────────────

def test_tiny_advance_not_zeroed():
    lines = [_line(i, 19997.00) for i in range(100)]
    shares = allocate_car_advances(1999.00, lines, "proportional", WHOLE_EUR)
    assert sum(shares.values()) == 1999
    assert sum(shares.values()) > 0


# ── single car rounds the stored total half-up ────────────────────────────────

def test_single_car_rounds_half_up():
    lines = [_line(10, 45750.00)]
    shares = allocate_car_advances(2287.50, lines, "proportional", WHOLE_EUR)
    assert shares[10] == 2288


# ── tie-break is input-order deterministic ────────────────────────────────────
# Identical-price cars leaving a 1-EUR remainder: the extra EUR goes to the FIRST
# car in input order. Every caller (forward render, storno reversal, final kurs)
# MUST feed cars in the same order (line_number) so they agree on which car gets
# it — otherwise a storno reverses a different split than the final books.

def test_tie_break_follows_input_order():
    shares = allocate_car_advances(5001.00, [_line(10, 56000.0), _line(20, 56000.0)],
                                   "proportional", WHOLE_EUR)
    assert (shares[10], shares[20]) == (2501, 2500)
    assert sum(shares.values()) == 5001


def test_reversed_input_order_moves_the_extra_euro():
    shares = allocate_car_advances(5001.00, [_line(20, 56000.0), _line(10, 56000.0)],
                                   "proportional", WHOLE_EUR)
    assert (shares[20], shares[10]) == (2501, 2500)
