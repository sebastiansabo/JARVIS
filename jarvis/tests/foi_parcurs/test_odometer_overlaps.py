"""Pure overlap detector behind the Rapoarte reconciliation report.

`overlap_rows(sessions)` flags any real session whose km_start falls below the
running max km_end of earlier (lower-odometer) sessions — two drives claiming km
the car had already passed. Mirrors the frontend `sessionAnomalies` walk and sits
next to `_rows_with_gaps` in the service layer.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.route_sheet_service import overlap_rows, date_inversion_rows


def _s(id, ks, ke, who='x', status='COMPLETED'):
    return {'id': id, 'km_start': ks, 'km_end': ke, 'client_name': who,
            'advisor_name': None, 'status': status,
            'departure_datetime': None, 'created_at': None}


def test_overlap_detected_when_start_below_prior_max_end():
    # #3 starts at 261 but the car was already at 283 (from #2) → overlap of 22.
    rows = overlap_rows([_s(1, 160, 261), _s(2, 261, 283), _s(3, 261, 312)])
    assert [r['id'] for r in rows] == [3]
    assert rows[0]['prior_max_end'] == 283
    assert rows[0]['overlap_km'] == 22


def test_no_overlap_for_contiguous_chain():
    assert overlap_rows([_s(1, 160, 261), _s(2, 261, 283), _s(3, 283, 312)]) == []


def test_planned_and_missed_are_skipped():
    # A PLANNED 0-0 booking and a MISSED no-show never moved the car → ignored,
    # and must not themselves be flagged nor flag the real drives around them.
    rows = overlap_rows([
        _s(1, 160, 261),
        _s(2, 0, 0, status='PLANNED'),
        _s(3, 261, 261, status='MISSED'),
        _s(4, 261, 312),
    ])
    assert rows == []


def test_row_carries_date_from_precomputed_date_field():
    # Repo rows carry a 'date' string (to_char of departure/created); the overlap
    # row surfaces it for the report.
    rows = overlap_rows([
        {**_s(1, 100, 200), 'date': '2026-09-04'},
        {**_s(2, 150, 180), 'date': '2026-09-05'},
    ])
    assert rows[0]['id'] == 2
    assert rows[0]['date'] == '2026-09-05'


def test_uses_advisor_name_when_no_client():
    # The overlapping drive (150 < prior max 200) is an internal one with no
    # client — its advisor name is used as the "who".
    rows = overlap_rows([_s(1, 100, 200), {**_s(2, 150, 180), 'client_name': None,
                                           'advisor_name': 'Internal Drv'}])
    assert [r['id'] for r in rows] == [2]
    assert rows[0]['who'] == 'Internal Drv'


# ── date_inversion_rows: the other anomaly the ⚠️ badge fires on ──────────────

def test_date_inversion_detected():
    # #2 is a higher-odometer drive dated BEFORE #1 (lower odometer) — impossible
    # when the odometer only moves forward → flagged.
    rows = date_inversion_rows([
        {**_s(1, 100, 200), 'date': '2026-09-10'},
        {**_s(2, 200, 300), 'date': '2026-09-05'},
    ])
    assert [r['id'] for r in rows] == [2]
    assert rows[0]['prior_max_date'] == '2026-09-10'
    assert rows[0]['date'] == '2026-09-05'


def test_no_inversion_when_dates_increase_with_odometer():
    rows = date_inversion_rows([
        {**_s(1, 100, 200), 'date': '2026-09-05'},
        {**_s(2, 200, 300), 'date': '2026-09-10'},
    ])
    assert rows == []


def test_inversion_skips_planned_and_missed():
    rows = date_inversion_rows([
        {**_s(1, 100, 200), 'date': '2026-09-10'},
        {**_s(2, 150, 150, status='MISSED'), 'date': '2026-09-01'},
        {**_s(3, 200, 300, status='PLANNED'), 'date': '2026-09-01'},
    ])
    assert rows == []


def test_inversion_uses_advisor_name_when_no_client():
    rows = date_inversion_rows([
        {**_s(1, 100, 200), 'date': '2026-09-10'},
        {**_s(2, 200, 300), 'client_name': None, 'advisor_name': 'Internal Drv', 'date': '2026-09-05'},
    ])
    assert rows[0]['who'] == 'Internal Drv'
