"""Version B: a proportional advance/proforma total is the SUM of each car's
rounded per-car slice, so the stored total equals Σ of the per-car lines the
allocator renders — and every car's advance rounds half up.

Regression: CTR-1561 (2LMN Vertrieb, AW International) — a bulk 5% advance on
8 cars (6 × 20290, 2 × 20412) stored its total as round(5% × Σprice) = 8128,
which forced the allocator to round four 20290 cars DOWN to 1014 (rest 19276)
to reconcile. The per-car-consistent total is 8132 (= 8 rounded slices), so
every car is 1015 / 19275.

The closing slice subtracts the ACTUAL prior bookings (not a fraction-implied
round), so a rest issued after a *pre-canonical* 5% proforma still balances to
the cars' prices (header == Σ lines).
"""
import os
import sys

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from accounting.facturare.services.advance_alloc import (  # noqa: E402
    proportional_total, track_prior_booked, anexa_car_allocations,
)

# CTR-1561: lines 1047..1052 at 20290, 1053..1054 at 20412.
PRICES = {1047: 20290.0, 1048: 20290.0, 1049: 20290.0, 1050: 20290.0,
          1051: 20290.0, 1052: 20290.0, 1053: 20412.0, 1054: 20412.0}
ALL_IDS = list(PRICES)
CONTRACT = int(sum(PRICES.values()))  # 162564


def _proforma(id_, total, lids=ALL_IDS):
    return {"id": id_, "invoice_type": "PROFORMA", "line_ids": lids,
            "total_amount_eur": total, "sequence_number": 1, "issued_date": "2026-07-30",
            "split_mode": "proportional", "round_decimals": False}


def test_bulk_5pct_total_is_sum_of_per_car_roundup():
    # 5% of 20290 = 1014.50 -> 1015 (x6); 5% of 20412 = 1020.60 -> 1021 (x2).
    assert proportional_total(0.05, ALL_IDS, PRICES) == 6 * 1015 + 2 * 1021  # 8132


def test_bulk_95pct_closing_is_residual_of_actual_prior():
    prior = track_prior_booked(ALL_IDS, [_proforma(1, 8132)], PRICES)  # canonical 5% -> 1015/1021
    assert proportional_total(0.95, ALL_IDS, PRICES, prior) == 6 * 19275 + 2 * 19391  # 154432


def test_5_and_95_partition_the_contract_exactly():
    prior = track_prior_booked(ALL_IDS, [_proforma(1, 8132)], PRICES)
    assert (proportional_total(0.05, ALL_IDS, PRICES)
            + proportional_total(0.95, ALL_IDS, PRICES, prior) == CONTRACT)  # 162564


def test_clean_percent_without_half_euro_is_unchanged():
    prices = {i: 20000.0 for i in range(1, 7)}  # 5% = 1000 exactly
    assert proportional_total(0.05, list(prices), prices) == 6000


def test_track_prior_booked_reads_canonical_proforma():
    prior = track_prior_booked(ALL_IDS, [_proforma(1, 8132)], PRICES)
    assert prior[1049] == 1015 and prior[1053] == 1021


def test_closing_balances_even_after_a_pre_canonical_proforma():
    # Finding #2: a 5% proforma stored the OLD way (8128) books 1014 on some cars;
    # the 95% residual must use that ACTUAL 1014 (-> 19276), so header == Σ lines
    # and the two documents still partition the contract (8128 + 154436 = 162564),
    # not 154432 (which would leave the anexa 4 € short of 100%).
    prior = track_prior_booked(ALL_IDS, [_proforma(1, 8128)], PRICES)
    rest = proportional_total(0.95, ALL_IDS, PRICES, prior)
    assert 8128 + rest == CONTRACT        # 154436, header == lines, anexa balances
    assert prior[1049] == 1014            # actual pre-canonical booking, not 1015


def test_cents_priced_full_proforma_rounds_each_line():
    # Finding #1 (math half): a 100% proforma on cents-priced cars sums rounded
    # prices (8 × round_half_up(20290.60) = 8 × 20291 = 162328), which exceeds the
    # exact Σprice (162324.80) — the state-machine capacity basis must match this.
    prices = {i: 20290.60 for i in range(8)}
    assert proportional_total(1.0, list(prices), prices) == 8 * 20291  # 162328


def test_canonical_total_makes_allocator_render_1015_for_every_car():
    five = proportional_total(0.05, ALL_IDS, PRICES)
    inv = {"id": 1, "invoice_type": "INVOICE", "line_ids": ALL_IDS,
           "total_amount_eur": five, "sequence_number": 1, "issued_date": "2026-07-31",
           "split_mode": "proportional", "round_decimals": False}
    shares = anexa_car_allocations([inv], PRICES)[1]
    assert all(shares[l] == 1015 for l in range(1047, 1053))
    assert shares[1053] == 1021 and shares[1054] == 1021
