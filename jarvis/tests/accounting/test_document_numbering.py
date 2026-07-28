import os, sys
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

from accounting.facturare.services.document_numbering import series_for, allocate


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
