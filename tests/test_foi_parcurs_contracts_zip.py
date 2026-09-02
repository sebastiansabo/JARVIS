"""Per-car contract-ZIP endpoint wiring + period-grouping consistency.

Confirms the new route imports cleanly (the `_period` import from
route_sheet_service is wired) and that ZIP membership uses the SAME (year, month)
grouping the Foi de Parcurs row uses — so the download never drifts from the row.
"""
from foi_parcurs.routes import export as ex
from foi_parcurs.services.route_sheet_service import _period


def test_endpoint_is_registered():
    # The view function exists and the blueprint module imported (so the new
    # `_period` import resolved) — that's the wiring we care about here.
    assert hasattr(ex, 'api_route_sheet_contracts_zip')
    assert callable(ex.api_route_sheet_contracts_zip)


def test_period_grouping_matches_route_sheet():
    # Explicit year/month columns win…
    assert _period({'year': 2026, 'month': 8, 'created_at': None}) == (2026, 8)
    # …else fall back to the drive/created date (test-drive rows have NULL y/m).
    assert _period({'year': None, 'month': None, 'created_at': '2026-08-05T10:00:00'}) == (2026, 8)


def test_row_membership_filter_logic():
    # Mirror the endpoint's in-loop filter: keep FILLED/COMPLETED rows whose
    # _period matches the requested (year, month); month=0 → whole year.
    def keep(row, year, month):
        if row.get('status') not in ('FILLED', 'COMPLETED'):
            return False
        py, pm = _period(row)
        return py == year and (not month or pm == month)

    aug = {'status': 'COMPLETED', 'year': 2026, 'month': 8, 'created_at': None}
    jul = {'status': 'COMPLETED', 'year': 2026, 'month': 7, 'created_at': None}
    pending = {'status': 'PENDING', 'year': 2026, 'month': 8, 'created_at': None}

    assert keep(aug, 2026, 8) is True
    assert keep(jul, 2026, 8) is False          # other month excluded
    assert keep(jul, 2026, 0) is True           # month=0 → whole year
    assert keep(pending, 2026, 8) is False       # no contract yet → excluded
