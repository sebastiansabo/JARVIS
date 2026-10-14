"""Chronological per-track per-car allocator — the CORRECT reconcile.

Must satisfy BOTH invariants simultaneously (the v1 fix, JAR-2027/8, satisfied
only the first and regressed the second → reverted JAR-2031/2):

  A) each document's cars sum to its stored total (CTR-790: bulk 10% proforma),
  B) a car's advances sum to its whole price (CTR-605 bulk-10%+90%, CTR-945 5/95%)

because a car's CLOSING slice books ``price − ACTUAL prior bookings`` (what
earlier invoices really booked), not ``price − round(price × fraction)``.
"""
import os
import sys

import pytest

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from accounting.facturare.services.advance_alloc import anexa_car_allocations  # noqa: E402


def inv(id_, itype, lids, total, seq, date, split="proportional", rd=False):
    return {"id": id_, "invoice_type": itype, "line_ids": lids, "total_amount_eur": total,
            "sequence_number": seq, "issued_date": date, "split_mode": split, "round_decimals": rd}


# ── A) CTR-790: single bulk proforma reconciles to its stored total ───────────

def test_ctr790_single_proforma_reconciles_to_11226():
    prices = {1: 56136.0, 2: 56136.0}
    a = anexa_car_allocations([inv(992, "PROFORMA", [1, 2], 11226, 1, "2026-07-23")], prices)
    assert a[992] == {1: 5613, 2: 5613}
    assert sum(a[992].values()) == 11226


# ── B) bulk 10% + per-car 90%: closing uses ACTUAL prior → both invariants ────

def test_bulk10_then_90_reconciles_price_and_doc():
    prices = {1: 21598.0, 2: 16047.0}
    a = anexa_car_allocations([
        inv(867, "PROFORMA", [1, 2], 3764, 1, "2026-03-27"),   # bulk 10%
        inv(924, "PROFORMA", [1], 19439, 2, "2026-05-26"),     # per-car 90% of car 1
    ], prices)
    assert sum(a[867].values()) == 3764                        # (A) bulk reconciles
    assert a[924][1] == 21598 - a[867][1]                      # closing = price − ACTUAL prior
    assert a[867][1] + a[924][1] == 21598                      # (B) advance+rest = price


def test_90_closing_does_not_leave_one_euro_gap():
    # The exact regression: whatever the bulk share, the 90% closes to the price.
    prices = {863: 21598.0}
    a = anexa_car_allocations([
        inv(867, "PROFORMA", [863], 2159, 1, "2026-03-27"),    # a 10% that booked 2159
        inv(924, "PROFORMA", [863], 19439, 2, "2026-05-26"),
    ], prices)
    assert a[867][863] + a[924][863] == 21598                  # not 21597


# ── B) CTR-945: 5% then 95%, separate proformas, single car ───────────────────

def test_ctr945_five_then_ninetyfive_reconciles():
    prices = {10: 45750.0}
    a = anexa_car_allocations([
        inv(915, "PROFORMA", [10], 2287.50, 1, "2026-05-13"),
        inv(1049, "PROFORMA", [10], 43462.50, 3, "2026-07-08"),
    ], prices)
    assert a[915][10] == 2288
    assert a[1049][10] == 43462                                # residual, not 43463
    assert a[915][10] + a[1049][10] == 45750


# ── tracks are independent: proforma track ≠ invoice track ────────────────────

def test_proforma_and_invoice_tracks_independent():
    prices = {1: 56136.0, 2: 56136.0}
    a = anexa_car_allocations([
        inv(992, "PROFORMA", [1, 2], 11226, 1, "2026-07-23"),
        inv(993, "INVOICE", [1, 2], 11226, 1, "2026-07-24"),   # confirms the proforma
    ], prices)
    assert a[992] == {1: 5613, 2: 5613}
    assert a[993] == {1: 5613, 2: 5613}                        # INVOICE not "closed" by PROFORMA


# ── FINAL track: a full final books the whole price ───────────────────────────

def test_full_final_books_whole_price():
    prices = {10: 21598.0}
    a = anexa_car_allocations([inv(9103699, "FINAL", [10], 21598, 1, "2026-07-06")], prices)
    assert a[9103699][10] == 21598


# ── zecimale (cents) mode keeps decimals and reconciles ───────────────────────

def test_zecimale_keeps_cents():
    prices = {i: 19997.0 for i in range(100)}
    a = anexa_car_allocations([inv(1, "PROFORMA", list(range(100)), 199970, 1, "2026-01-01", rd=True)], prices)
    assert all(v == pytest.approx(1999.70) for v in a[1].values())
    assert sum(a[1].values()) == pytest.approx(199970.0)


# ── equal split distributes the total ─────────────────────────────────────────

def test_equal_split_distributes_total():
    prices = {i: 19997.0 for i in range(100)}
    a = anexa_car_allocations([inv(1, "PROFORMA", list(range(100)), 199900, 1, "2026-01-01", split="equal")], prices)
    assert sum(a[1].values()) == 199900
    assert all(v == 1999 for v in a[1].values())
