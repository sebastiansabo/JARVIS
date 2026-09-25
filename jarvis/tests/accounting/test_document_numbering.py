import os, sys
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

from accounting.facturare.services.document_numbering import series_for, allocate, per_car_number


def test_series_split():
    assert series_for("PROFORMA") == "proforma"
    for t in ("INVOICE", "STORNO", "FINAL"):
        assert series_for(t) == "fiscal"


def test_per_car_increments_by_position():
    rows = allocate("INVOICE", 9103042, "per_car", [838, 839, 840, 841, 842])
    assert [r["document_number"] for r in rows] == [9103042, 9103043, 9103044, 9103045, 9103046]
    assert [r["position"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r["line_id"] for r in rows] == [838, 839, 840, 841, 842]
    assert all(r["series"] == "fiscal" for r in rows)


def test_single_doc_shares_base_number():
    rows = allocate("INVOICE", 9103042, "single_doc", [838, 839, 840])
    assert [r["document_number"] for r in rows] == [9103042, 9103042, 9103042]


def test_storno_single_car_uses_base():
    rows = allocate("STORNO", 9103805, "per_car", [840])
    assert rows == [{"line_id": 840, "position": 0, "document_number": 9103805, "series": "fiscal"}]


def test_none_base_yields_none_numbers():
    rows = allocate("PROFORMA", None, "per_car", [1, 2])
    assert [r["document_number"] for r in rows] == [None, None]
    assert all(r["series"] == "proforma" for r in rows)


# ── per_car_number: the number a specific car carries on a document ──────────
# Regression for the Aurento / CTR-338 report: an advance invoice printed the
# proforma's BASE number (1290) for every car instead of that car's actual
# per-car proforma number. Proforma seq=21 (base 1290) covers 13 cars in the
# stored order [757,755,...,738]; order 507794 == line 738 sits at position 12,
# so its proforma number is 1290+12 = 1302.
_PROFORMA_LINES = [757, 755, 754, 753, 752, 751, 750, 746, 745, 743, 741, 740, 738]
_PROFORMA_STORED = {lid: 1290 + i for i, lid in enumerate(_PROFORMA_LINES)}  # 757->1290 … 738->1302


def test_per_car_number_prefers_stored_map():
    # The car actually invoiced (line 738) must show 1302, not the base 1290.
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 738, stored=_PROFORMA_STORED) == 1302
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 757, stored=_PROFORMA_STORED) == 1290
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 740, stored=_PROFORMA_STORED) == 1301


def test_per_car_number_is_independent_of_advance_invoice_ordering():
    # The bug: a single-car advance invoice for line 738 rendered it at page
    # index 0 and printed base+0 = 1290. The number must depend on the car, not
    # on the advance invoice's own page index — so line 738 is always 1302.
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 738, stored=_PROFORMA_STORED) == 1302


def test_per_car_number_positional_fallback_uses_proforma_order():
    # No stored map (legacy pre-backfill): fall back to base + position within
    # the PROFORMA's own line order — never the advance invoice's index.
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 738, stored=None) == 1302
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 757, stored={}) == 1290


def test_per_car_number_positional_over_full_anexa_order():
    # Whole-anexa proforma (line_ids NULL) with no stored map: the route passes
    # the anexa's full ordered line list, so the fallback must still yield
    # base + position over THAT list (regression guard for the NULL-line_ids
    # legacy slice — otherwise every car printed the base number).
    anexa_lines = [738, 739, 740]  # anexa line_number order supplied by the route
    assert per_car_number(1290, "per_car", anexa_lines, 738, stored=None) == 1290
    assert per_car_number(1290, "per_car", anexa_lines, 739, stored=None) == 1291
    assert per_car_number(1290, "per_car", anexa_lines, 740, stored=None) == 1292


def test_per_car_number_single_doc_shares_base():
    assert per_car_number(838, "single_doc", [738, 739, 740], 740, stored=None) == 838


def test_per_car_number_none_base():
    assert per_car_number(None, "per_car", [1, 2], 2, stored=None) is None


def test_per_car_number_unknown_line_falls_back_to_base():
    assert per_car_number(1290, "per_car", _PROFORMA_LINES, 99999, stored={}) == 1290
