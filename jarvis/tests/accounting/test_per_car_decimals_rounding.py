"""Per-car rounding: decimals (zecimale) mode + snap-to-zero regression.

Covers CTR-1646 / anexa 49 (100 × 19.997 € Golf Prime), where:

  * a 10% advance of 199.970 € split over 100 cars rounded each car half-up to a
    whole 2.000 €, so 100 × 2.000 = 200.000 € overshot the 199.970 € proforma by
    30 €. The user wants "rounding only on the decimals": each car books
    1.999,70 € so the slices reconcile to the invoice total exactly.

  * entering a small total (1.999 € across 100 cars = a 0,0999% advance) made
    `_snap_pct` snap the fraction down to 0%, so every car rendered 0,00 €.
"""
import os
import sys
from decimal import Decimal

import pytest

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from accounting.facturare import routes_orders  # noqa: E402

CENTS = Decimal("0.01")


# ── snap-to-zero regression ───────────────────────────────────────────────────

def test_snap_pct_never_zeroes_a_positive_advance():
    # 1.999 € total across 100 × 19.997 € cars = 0,0999% — must NOT snap to 0%.
    pct = routes_orders._snap_pct(1999, 100 * 19997)
    assert pct > 0


def test_snap_pct_still_snaps_near_whole_percent():
    # A 10% advance stored as a rounded total still snaps cleanly to 0.10.
    assert routes_orders._snap_pct(199970, 100 * 19997) == pytest.approx(0.10)


# ── decimals (zecimale) mode: keep 2 decimals per car ─────────────────────────

def test_proportional_slice_keeps_cents_in_decimals_mode():
    # 19.997 × 10% = 1.999,70 — kept, not rounded up to 2.000.
    assert routes_orders._car_slice_eur(19997, 0.10, [], CENTS) == pytest.approx(1999.70)


def test_equal_split_keeps_cents_in_decimals_mode():
    # 199.970 / 100 = 1.999,70 per car in equal mode.
    got = routes_orders._per_car_advance_eur(199970, 19997, 100 * 19997,
                                             "equal", 100, quant=CENTS)
    assert got == pytest.approx(1999.70)


def test_decimals_advance_plus_rest_reconcile_to_selling():
    advance = routes_orders._car_slice_eur(19997, 0.10, [], CENTS)
    rest = routes_orders._car_slice_eur(19997, 0.90, [0.10], CENTS)
    assert advance + rest == pytest.approx(19997.00)


def test_decimals_per_car_sum_reconciles_to_invoice_total():
    per_car = routes_orders._car_slice_eur(19997, 0.10, [], CENTS)
    assert per_car * 100 == pytest.approx(199970.00)


# ── whole-EUR mode (default) unchanged ────────────────────────────────────────

def test_whole_mode_still_rounds_half_up():
    # Default quantum is a whole EUR: 1.999,70 -> 2.000.
    assert routes_orders._car_slice_eur(19997, 0.10, []) == 2000
    assert routes_orders._per_car_advance_eur(199970, 19997, 100 * 19997,
                                              "equal", 100) == 2000
