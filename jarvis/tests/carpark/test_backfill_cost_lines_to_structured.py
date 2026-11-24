"""Tests for the Task 4 backfill:
`jarvis/scripts/backfill_cost_lines_to_structured.py` — migrates each
vehicle's legacy acquisition `cost_lines` JSON (a TEXT column holding a JSON
array) into structured `carpark_vehicle_costs` rows under a new `achizitie`
cost line, then nulls `cost_lines`.

This is accounting-sensitive: a double-count or VAT inflation would
silently corrupt car economics. The pure-function tests (`parse_lines`,
`build_cost_row`) need no DB. The DB-backed tests below exercise `run()`
against the real localhost Postgres (same REAL_DB_AVAILABLE probe/skip dance
as test_dispo_repository_sql.py / test_backfill_acq_currency.py).

Sentinel company_id=990006 — distinct from every other sentinel already in
use in this package (990001 dispo_seed, 990002 phase2_e2e/cost_model_profit,
990003 carpark_scheduler/import_centralizator, 990004 import_centralizator's
OTHER_COMPANY_ID, 990005 backfill_acq_currency).

Every `run(...)` call here passes `company_id=TEST_COMPANY_ID`, so the audit
(and therefore the migration) is scoped to this test's own sentinel rows —
it never audits or mutates real/other-company data. The unscoped full-table
behavior (`company_id=None`, the prod backfill path) is deliberately NOT
exercised against this shared dev DB.
"""
import json
import os
import sys
from datetime import date

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402

from database import get_db, get_cursor, release_db  # noqa: E402

# jarvis/scripts/ is a real package (has __init__.py, like
# accounting/facturare/scripts/), and JARVIS_ROOT is pinned at sys.path[0]
# above, so this resolves to jarvis/scripts even on a machine that has an
# unrelated top-level `scripts` package further down sys.path.
import scripts.backfill_cost_lines_to_structured as backfill_module  # noqa: E402
from scripts.backfill_cost_lines_to_structured import (  # noqa: E402
    parse_lines, parse_lines_strict, build_cost_row, run, NULL_COST_LINES_SQL,
)

from .conftest import REAL_DB_AVAILABLE  # noqa: E402

TEST_COMPANY_ID = 990006

VIN_BASIC = 'TESTCOSTLN0000001'
VIN_APPEND = 'TESTCOSTLN0000002'
VIN_NULL_EUR = 'TESTCOSTLN0000003'
VIN_MALFORMED = 'TESTCOSTLN0000004'
VIN_BAD_DATE = 'TESTCOSTLN0000005'
VIN_ATOMIC_OK = 'TESTCOSTLN0000006'
VIN_ATOMIC_FAIL = 'TESTCOSTLN0000007'
assert len(VIN_BASIC) == 17
assert len(VIN_APPEND) == 17
assert len(VIN_NULL_EUR) == 17
assert len(VIN_MALFORMED) == 17
assert len(VIN_BAD_DATE) == 17
assert len(VIN_ATOMIC_OK) == 17
assert len(VIN_ATOMIC_FAIL) == 17

JSON_BASIC = json.dumps([
    {'type': 'Transport', 'description': '', 'date': '2026-01-02', 'lei': 1000, 'kurs': 5, 'eur': 200},
    {'type': 'Recondiționare', 'description': '', 'date': '', 'lei': None, 'kurs': None, 'eur': 300},
])

JSON_APPEND = json.dumps([
    {'type': 'Taxe', 'description': 'vamale', 'date': '2026-02-01', 'lei': None, 'kurs': None, 'eur': 120},
])

JSON_NULL_EUR = json.dumps([
    {'type': 'Transport', 'description': 'necunoscut', 'date': '2026-01-05', 'lei': None, 'kurs': None, 'eur': None},
])

# Non-empty but unparseable: a truncated JSON blob (e.g. a half-written
# value from a crashed editor save). Must be left UNTOUCHED, not nulled.
MALFORMED_COST_LINES = '[{"type":"Transport","eur":200},{BROKEN'

# Valid JSON, valid entry, but a `date` that is not a parseable date at all
# (e.g. typed into an old freeform editor before `date` was a <input
# type=date>). FW1: this must fall back to the vehicle date chain, never
# reach the INSERT as a raw 'N/A' string and halt the run.
JSON_BAD_DATE = json.dumps([
    {'type': 'Transport', 'description': '', 'date': 'N/A', 'lei': None, 'kurs': None, 'eur': 150},
])

# FW2 atomicity regression fixtures: two otherwise-ordinary migratable cars.
JSON_ATOMIC_OK = json.dumps([
    {'type': 'Transport', 'description': '', 'date': '2026-01-02', 'lei': None, 'kurs': None, 'eur': 100},
])

JSON_ATOMIC_FAIL = json.dumps([
    {'type': 'Transport', 'description': '', 'date': '2026-01-03', 'lei': None, 'kurs': None, 'eur': 200},
])


@pytest.fixture
def require_real_db():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping cost_lines backfill DB-backed test'
        )


def _delete_seed():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture
def cost_lines_seed():
    """Seeds three vehicles under TEST_COMPANY_ID:

      - 'basic': cost_lines = two JSON entries (Transport 200 EUR with a real
        date; Recondiționare 300 EUR with an EMPTY date string, to exercise
        the entry.date -> vehicle date -> CURRENT_DATE fallback chain). No
        pre-existing achizitie cost line.
      - 'append': ALREADY has an achizitie cost line with one child cost
        (amount=50), simulating the accepted pre-backfill user-add window —
        PLUS a non-null cost_lines (one entry, 120 EUR). The backfill must
        append to the SAME line, not spawn a second one.
      - 'null_eur': cost_lines = one entry whose `eur` is null — the
        backfill must insert zero cost rows for it, yet still null out
        cost_lines (its total was 0, not "nothing to do").
      - 'malformed': cost_lines = a non-empty but UNPARSEABLE blob
        (truncated JSON). The backfill must leave it COMPLETELY untouched
        (not nulled, not migrated) and surface it in needs_review.
      - 'bad_date': cost_lines = one VALID JSON entry (eur=150) whose
        `date` is a non-empty but UNPARSEABLE string ('N/A' — FW1). No
        acquisition_date set, so the fallback resolves to CURRENT_DATE. The
        backfill must migrate this car (not crash, not halt the run) using
        the fallback date.

    Yields {'basic': id, 'append': id, 'append_line_id': id, 'null_eur': id,
            'malformed': id, 'bad_date': id}. Teardown deletes every
    carpark_vehicles row for TEST_COMPANY_ID (cost lines/costs cascade via
    ON DELETE CASCADE) and asserts zero remain.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping cost_lines backfill DB-backed test'
        )

    _delete_seed()  # defensive: clean up any leftover rows from a crashed prior run

    conn = get_db()
    ids = {}
    try:
        cur = get_cursor(conn)

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_BASIC, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_BASIC))
        ids['basic'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_APPEND, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_APPEND))
        ids['append'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicle_cost_lines (vehicle_id, cost_type, planned_amount, currency)
            VALUES (%s, 'achizitie', 0, 'EUR')
            RETURNING id
        ''', (ids['append'],))
        ids['append_line_id'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicle_costs
                (vehicle_id, cost_line_id, cost_type, description, amount, currency, vat_rate, vat_amount)
            VALUES (%s, %s, 'achizitie', 'Pre-existing manual cost', 50, 'EUR', 0, 0)
        ''', (ids['append'], ids['append_line_id']))
        cur.execute('''
            UPDATE carpark_vehicle_cost_lines SET spent_amount = 50 WHERE id = %s
        ''', (ids['append_line_id'],))

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_NULL_EUR, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_NULL_EUR))
        ids['null_eur'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_MALFORMED, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, MALFORMED_COST_LINES))
        ids['malformed'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_BAD_DATE, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_BAD_DATE))
        ids['bad_date'] = cur.fetchone()['id']

        conn.commit()
    finally:
        release_db(conn)

    try:
        yield ids
    finally:
        _delete_seed()
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (TEST_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={TEST_COMPANY_ID}'
        )


@pytest.fixture
def atomicity_seed():
    """FW2: seeds TWO otherwise-ordinary migratable vehicles under
    TEST_COMPANY_ID to pin the per-car atomicity fix (`conn.autocommit =
    False` in `run()`):

      - 'ok': migratable (100 EUR), inserted FIRST so it sorts first in the
        audit's `ORDER BY id` and is fully committed BEFORE 'fail' is even
        reached by the for loop.
      - 'fail': migratable (200 EUR) too — the TEST (not this fixture)
        monkeypatches `get_cursor` so the NULL_COST_LINES_SQL update raises
        for this specific vehicle_id, simulating a crash AFTER the
        achizitie cost row is INSERTed but BEFORE the per-car commit. If
        autocommit were effectively True, 'fail' would be left
        half-migrated: a durably-written achizitie cost row with
        cost_lines still non-null — the exact "both at once" state the
        module docstring says must be impossible. With autocommit=False,
        the whole per-car transaction must roll back, leaving 'fail'
        exactly as it started.

    Yields {'ok': id, 'fail': id}. Teardown deletes every carpark_vehicles
    row for TEST_COMPANY_ID (same pattern as `cost_lines_seed`) and asserts
    zero remain.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping cost_lines backfill DB-backed test'
        )

    _delete_seed()  # defensive: clean up any leftover rows from a crashed prior run

    conn = get_db()
    ids = {}
    try:
        cur = get_cursor(conn)

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_ATOMIC_OK, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_ATOMIC_OK))
        ids['ok'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, category, company_id, cost_lines)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (VIN_ATOMIC_FAIL, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, JSON_ATOMIC_FAIL))
        ids['fail'] = cur.fetchone()['id']

        conn.commit()
    finally:
        release_db(conn)

    try:
        yield ids
    finally:
        _delete_seed()
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (TEST_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={TEST_COMPANY_ID}'
        )


class _RaiseOnNullForVehicle:
    """Cursor proxy used by the FW2 atomicity test: delegates every call to
    the real cursor UNCHANGED, except it raises when NULL_COST_LINES_SQL is
    executed for one specific vehicle_id — simulating a crash between the
    achizitie INSERT(s)/RECALC and the per-car `conn.commit()`. This is the
    injection point the FW2 brief calls out: "after the child-cost
    INSERT(s), before/at the cost_lines=NULL update."
    """

    def __init__(self, real_cursor, trigger_vehicle_id):
        self._cursor = real_cursor
        self._trigger_vehicle_id = trigger_vehicle_id

    def execute(self, query, params=None):
        if query == NULL_COST_LINES_SQL and params == (self._trigger_vehicle_id,):
            raise RuntimeError(
                'FW2 injected failure: simulated crash before the '
                'cost_lines NULL update commits'
            )
        return self._cursor.execute(query, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def _fetch_vehicle(vehicle_id):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT cost_lines FROM carpark_vehicles WHERE id = %s', (vehicle_id,))
        return cur.fetchone()
    finally:
        release_db(conn)


def _fetch_achizitie_lines(vehicle_id):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('''
            SELECT id, spent_amount, currency FROM carpark_vehicle_cost_lines
            WHERE vehicle_id = %s AND cost_type = 'achizitie'
            ORDER BY id
        ''', (vehicle_id,))
        return cur.fetchall()
    finally:
        release_db(conn)


def _fetch_costs(cost_line_id):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('''
            SELECT amount, currency, vat_rate, vat_amount, cost_type, description, observation, date
            FROM carpark_vehicle_costs WHERE cost_line_id = %s ORDER BY id
        ''', (cost_line_id,))
        return cur.fetchall()
    finally:
        release_db(conn)


# ─────────────────────────────────────────────────────────────────────────
# parse_lines — pure-function guards (no DB)
# ─────────────────────────────────────────────────────────────────────────

def test_parse_lines_returns_list_of_dicts():
    raw = '[{"type":"Transport","description":"ro","date":"2026-01-02","lei":1000,"kurs":5,"eur":200}]'
    result = parse_lines(raw)
    assert len(result) == 1
    assert result[0]['type'] == 'Transport'
    assert result[0]['eur'] == 200


@pytest.mark.parametrize('raw', ['', '[]', 'not json', None])
def test_parse_lines_empty_or_invalid_returns_empty_list(raw):
    assert parse_lines(raw) == []


# ─────────────────────────────────────────────────────────────────────────
# parse_lines_strict — distinguishes "clean parse" from "malformed" so the
# backfill never nulls a malformed-but-non-empty accounting column.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,expected_len', [
    (None, 0),           # empty -> clean, nothing to migrate
    ('', 0),             # empty -> clean
    ('[]', 0),           # valid empty list -> clean
    ('[{"eur":1}]', 1),  # valid list -> clean
])
def test_parse_lines_strict_ok_for_empty_or_valid(raw, expected_len):
    ok, entries = parse_lines_strict(raw)
    assert ok is True
    assert len(entries) == expected_len


@pytest.mark.parametrize('raw', [
    'not json',                       # not JSON at all
    '[{"type":"Transport","eur":200},{BROKEN',  # truncated array
    '{"eur":1}',                      # valid JSON but an object, not a list
    '42',                             # valid JSON but a scalar, not a list
])
def test_parse_lines_strict_flags_malformed_non_empty(raw):
    ok, entries = parse_lines_strict(raw)
    assert ok is False
    assert entries == []


# ─────────────────────────────────────────────────────────────────────────
# build_cost_row — pure-function guards (no DB)
# ─────────────────────────────────────────────────────────────────────────

def test_build_cost_row_from_full_entry():
    entry = {'type': 'Transport', 'description': 'ro', 'date': '2026-01-02',
              'lei': 1000, 'kurs': 5, 'eur': 200}
    vehicle = {'acquisition_date': date(2025, 1, 1), 'created_at': None}
    row = build_cost_row(entry, vehicle)
    assert row['amount'] == 200
    assert row['currency'] == 'EUR'
    assert row['vat_rate'] == 0
    assert row['vat_amount'] == 0
    assert row['cost_type'] == 'achizitie'
    assert row['description'] == 'Transport: ro'
    assert 'LEI=1000' in row['observation']
    assert 'kurs=5' in row['observation']
    assert row['date'] == '2026-01-02'


def test_build_cost_row_null_eur_returns_none():
    entry = {'type': 'Transport', 'description': 'x', 'date': '2026-01-02',
              'lei': None, 'kurs': None, 'eur': None}
    assert build_cost_row(entry, {'acquisition_date': date.today()}) is None


def test_build_cost_row_non_numeric_eur_returns_none():
    entry = {'type': 'Transport', 'eur': 'not-a-number'}
    assert build_cost_row(entry, {'acquisition_date': date.today()}) is None


def test_build_cost_row_type_only_description():
    entry = {'type': 'Transport', 'description': '', 'eur': 50}
    vehicle = {'acquisition_date': date.today()}
    row = build_cost_row(entry, vehicle)
    assert row['description'] == 'Transport'


def test_build_cost_row_legacy_label_amount_fallback():
    # Original freeform shape before {type,description,date,lei,kurs,eur} —
    # see schema_incremental.py's "[{label, amount}]" column comment.
    entry = {'label': 'Reparatie motor', 'amount': 75}
    vehicle = {'acquisition_date': date.today()}
    row = build_cost_row(entry, vehicle)
    assert row['amount'] == 75
    assert row['description'] == 'Reparatie motor'


def test_build_cost_row_date_falls_back_to_vehicle_acquisition_date():
    entry = {'type': 'X', 'eur': 10, 'date': ''}
    vehicle = {'acquisition_date': date(2024, 6, 15), 'created_at': None}
    row = build_cost_row(entry, vehicle)
    assert row['date'] == date(2024, 6, 15)


def test_build_cost_row_date_falls_back_to_current_date_when_vehicle_has_no_date():
    entry = {'type': 'X', 'eur': 10, 'date': ''}
    vehicle = {'acquisition_date': None, 'created_at': None}
    row = build_cost_row(entry, vehicle)
    assert row['date'] == date.today()


def test_build_cost_row_unparseable_date_falls_back_instead_of_raising():
    # A non-empty but garbage `date` (e.g. 'N/A' typed into an old freeform
    # editor) must NOT be passed through to the INSERT as-is — Postgres
    # would reject it mid-car and halt the entire backfill run (see FW1).
    # It must degrade to the SAME fallback chain as an empty date.
    entry = {'type': 'X', 'eur': 10, 'date': 'N/A'}
    vehicle = {'acquisition_date': date(2024, 6, 15), 'created_at': None}
    row = build_cost_row(entry, vehicle)
    assert row is not None
    assert row['date'] == date(2024, 6, 15)


def test_build_cost_row_unparseable_date_falls_back_to_current_date_when_no_vehicle_date():
    entry = {'type': 'X', 'eur': 10, 'date': 'N/A'}
    vehicle = {'acquisition_date': None, 'created_at': None}
    row = build_cost_row(entry, vehicle)
    assert row['date'] == date.today()


# ─────────────────────────────────────────────────────────────────────────
# run() — DB-backed, always scoped to the sentinel company
# ─────────────────────────────────────────────────────────────────────────

def test_migration_creates_achizitie_rows_and_nulls_cost_lines_then_is_idempotent(
    require_real_db, cost_lines_seed
):
    vehicle_id = cost_lines_seed['basic']

    result = run(apply=True, company_id=TEST_COMPANY_ID)
    assert vehicle_id in result['migrated']

    lines = _fetch_achizitie_lines(vehicle_id)
    assert len(lines) == 1, 'exactly one achizitie cost line must exist'
    line = lines[0]
    assert float(line['spent_amount']) == 500.0

    costs = _fetch_costs(line['id'])
    assert len(costs) == 2
    amounts = sorted(float(c['amount']) for c in costs)
    assert amounts == [200.0, 300.0]
    for c in costs:
        assert c['currency'] == 'EUR'
        assert float(c['vat_rate']) == 0.0
        assert float(c['vat_amount']) == 0.0
        assert c['cost_type'] == 'achizitie'

    # The second entry's date was an empty string -> falls back to the
    # vehicle's date (CURRENT_DATE, since the seeded row didn't set
    # acquisition_date explicitly and the column defaults to CURRENT_DATE).
    second = next(c for c in costs if float(c['amount']) == 300.0)
    assert second['date'] == date.today()

    vehicle_row = _fetch_vehicle(vehicle_id)
    assert vehicle_row['cost_lines'] is None

    # Idempotency: migrated cars have NULL cost_lines, so a re-run is a
    # true no-op — the audit query no longer selects this vehicle at all.
    result2 = run(apply=True, company_id=TEST_COMPANY_ID)
    assert vehicle_id not in result2['migrated']
    assert vehicle_id not in result2['skipped']
    assert vehicle_id not in result2['audited']

    lines_after = _fetch_achizitie_lines(vehicle_id)
    assert len(lines_after) == 1
    costs_after = _fetch_costs(lines_after[0]['id'])
    assert len(costs_after) == 2, 're-run must not duplicate rows'

    vehicle_row_after = _fetch_vehicle(vehicle_id)
    assert vehicle_row_after['cost_lines'] is None


def test_migration_appends_to_pre_existing_achizitie_line(require_real_db, cost_lines_seed):
    vehicle_id = cost_lines_seed['append']
    pre_existing_line_id = cost_lines_seed['append_line_id']

    lines_before = _fetch_achizitie_lines(vehicle_id)
    assert len(lines_before) == 1
    assert len(_fetch_costs(pre_existing_line_id)) == 1

    result = run(apply=True, company_id=TEST_COMPANY_ID)
    assert vehicle_id in result['migrated']

    lines_after = _fetch_achizitie_lines(vehicle_id)
    assert len(lines_after) == 1, 'must append to the existing line, never spawn a second one'
    assert lines_after[0]['id'] == pre_existing_line_id

    costs = _fetch_costs(pre_existing_line_id)
    assert len(costs) == 2
    amounts = sorted(float(c['amount']) for c in costs)
    assert amounts == [50.0, 120.0]
    assert float(lines_after[0]['spent_amount']) == 170.0

    vehicle_row = _fetch_vehicle(vehicle_id)
    assert vehicle_row['cost_lines'] is None


def test_migration_null_eur_entry_inserts_no_row_but_nulls_cost_lines(
    require_real_db, cost_lines_seed
):
    vehicle_id = cost_lines_seed['null_eur']

    result = run(apply=True, company_id=TEST_COMPANY_ID)
    assert vehicle_id in result['skipped']
    assert vehicle_id not in result['migrated']

    lines = _fetch_achizitie_lines(vehicle_id)
    assert len(lines) == 0, 'a null-eur-only car must not spawn an achizitie line at all'

    vehicle_row = _fetch_vehicle(vehicle_id)
    assert vehicle_row['cost_lines'] is None, (
        'cost_lines must still be nulled even though its only entry was skippable '
        '(its total was 0, not "nothing to do")'
    )


def test_malformed_cost_lines_is_left_untouched_and_flagged_for_review(
    require_real_db, cost_lines_seed
):
    vehicle_id = cost_lines_seed['malformed']
    before = _fetch_vehicle(vehicle_id)
    assert before['cost_lines'] == MALFORMED_COST_LINES

    result = run(apply=True, company_id=TEST_COMPANY_ID)

    assert vehicle_id in result['needs_review']
    assert vehicle_id not in result['migrated']
    assert vehicle_id not in result['skipped']

    # No rows written: no achizitie line spawned for this car.
    lines = _fetch_achizitie_lines(vehicle_id)
    assert len(lines) == 0

    # Critically: the malformed column is NOT nulled — silently dropping a
    # non-empty accounting blob we couldn't parse would be irreversible loss.
    after = _fetch_vehicle(vehicle_id)
    assert after['cost_lines'] == MALFORMED_COST_LINES, (
        'a malformed-but-non-empty cost_lines must be left exactly as-is for '
        'manual review, never nulled'
    )


def test_unparseable_entry_date_migrates_with_fallback_date_no_crash(
    require_real_db, cost_lines_seed
):
    # FW1: a clean-JSON entry whose `date` is non-empty but unparseable
    # ('N/A') must not blow up the INSERT and halt the run — it must fall
    # back to the vehicle date chain (here: CURRENT_DATE, since this
    # vehicle has no acquisition_date) and migrate normally.
    vehicle_id = cost_lines_seed['bad_date']

    result = run(apply=True, company_id=TEST_COMPANY_ID)
    assert vehicle_id in result['migrated']
    assert vehicle_id not in result['needs_review']

    lines = _fetch_achizitie_lines(vehicle_id)
    assert len(lines) == 1
    assert float(lines[0]['spent_amount']) == 150.0

    costs = _fetch_costs(lines[0]['id'])
    assert len(costs) == 1
    assert float(costs[0]['amount']) == 150.0
    assert costs[0]['date'] == date.today(), (
        "an unparseable 'N/A' date must fall back to the vehicle's date "
        'chain (CURRENT_DATE here), not reach Postgres as raw text'
    )

    vehicle_row = _fetch_vehicle(vehicle_id)
    assert vehicle_row['cost_lines'] is None


def test_per_car_commit_is_atomic_on_mid_car_failure(
    require_real_db, atomicity_seed, monkeypatch
):
    """FW2: locks the `conn.autocommit = False` per-car atomicity fix.

    Injects a failure exactly at the NULL_COST_LINES_SQL update for the
    SECOND seeded car — i.e. AFTER its achizitie cost row is already
    INSERTed on the (still uncommitted) per-car transaction, but AT the
    statement that would otherwise commit it alongside the cost_lines
    NULL — and proves the whole per-car write rolls back atomically: the
    failing car ends up with cost_lines INTACT and ZERO achizitie
    lines/rows, while the FIRST car (already committed via its own
    `conn.commit()` before the second car was even processed) stays
    migrated. This is the regression autocommit=True would reintroduce:
    a durably-written achizitie row alongside a non-null cost_lines on the
    failing car.
    """
    ok_id = atomicity_seed['ok']
    fail_id = atomicity_seed['fail']

    real_get_cursor = backfill_module.get_cursor

    def fake_get_cursor(conn):
        return _RaiseOnNullForVehicle(real_get_cursor(conn), fail_id)

    monkeypatch.setattr(backfill_module, 'get_cursor', fake_get_cursor)

    before_fail = _fetch_vehicle(fail_id)
    assert before_fail['cost_lines'] == JSON_ATOMIC_FAIL

    with pytest.raises(RuntimeError, match='FW2 injected failure'):
        run(apply=True, company_id=TEST_COMPANY_ID)

    # The failing car: cost_lines must be EXACTLY as it started, and ZERO
    # achizitie cost lines/rows must exist — proving the achizitie
    # INSERT(s) rolled back together with the aborted NULL update
    # (atomic, not half-committed).
    after_fail = _fetch_vehicle(fail_id)
    assert after_fail['cost_lines'] == JSON_ATOMIC_FAIL, (
        'a mid-car failure must leave cost_lines untouched — autocommit=False '
        'must make the achizitie INSERT(s) + NULL update a single atomic unit'
    )
    fail_lines = _fetch_achizitie_lines(fail_id)
    assert len(fail_lines) == 0, (
        'the failing car must have ZERO achizitie cost lines after rollback — '
        'an orphaned line/cost row here would mean the per-car write was NOT '
        'atomic (i.e. autocommit was effectively True)'
    )

    # The already-committed FIRST car must be unaffected by the SECOND
    # car's later failure — proving the commit boundary is per-car, not
    # all-or-nothing across the whole run.
    ok_lines = _fetch_achizitie_lines(ok_id)
    assert len(ok_lines) == 1
    assert float(ok_lines[0]['spent_amount']) == 100.0
    ok_vehicle = _fetch_vehicle(ok_id)
    assert ok_vehicle['cost_lines'] is None, 'the already-committed first car must stay migrated'


def test_dry_run_writes_nothing(require_real_db, cost_lines_seed):
    vehicle_id = cost_lines_seed['basic']
    before = _fetch_vehicle(vehicle_id)
    assert before['cost_lines'] is not None

    result = run(apply=False, company_id=TEST_COMPANY_ID)
    assert vehicle_id in result['migrated']  # eligible/"would migrate", but no write

    after = _fetch_vehicle(vehicle_id)
    assert after['cost_lines'] == before['cost_lines'], 'dry-run must not touch cost_lines'

    lines = _fetch_achizitie_lines(vehicle_id)
    assert len(lines) == 0, 'dry-run must not create any achizitie cost line'
