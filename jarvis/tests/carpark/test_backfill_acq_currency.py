"""DB-backed idempotency test for the Task 8 RON-convention acquisition-price
backfill (`jarvis/scripts/backfill_acq_currency.py`).

Runs against the real localhost Postgres DB (same REAL_DB_AVAILABLE probe/skip
dance as test_dispo_repository_sql.py / test_import_centralizator.py).

Sentinel company_id=990005 — distinct from every other sentinel already in
use in this package (990001 dispo_seed, 990002 phase2_e2e/cost_model_profit,
990003 carpark_scheduler/import_centralizator, 990004 import_centralizator's
OTHER_COMPANY_ID).

NOTE: `run()` audits/converts every `carpark_vehicles` row with
acquisition_currency='RON' across the WHOLE table — that's its job (see the
script's module docstring). This dev DB already has one such row from earlier
manual editor testing (a real instance of exactly the bug this script fixes),
so calling `run(apply=True)` here also permanently converts it. That mirrors
the documented precedent in
tests/accounting/test_backfill_document_numbers.py: the assertions below only
pin down OUR seeded rows, and fixing any other real legacy row along the way
is the intended behavior of an idempotent backfill, not a test-isolation bug.
"""
import importlib.util
import os
import sys

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402

from database import get_db, get_cursor, release_db  # noqa: E402

from .conftest import REAL_DB_AVAILABLE  # noqa: E402

# Load the script by file path rather than `import scripts.backfill_acq_currency`:
# jarvis/scripts/ has no __init__.py (matching its sibling scripts), and this
# machine also has an unrelated top-level `scripts` package earlier on
# sys.path (a different repo checkout's ops scripts) that would otherwise win
# the namespace-package resolution and shadow this module entirely.
_SCRIPT_PATH = os.path.join(JARVIS_ROOT, 'scripts', 'backfill_acq_currency.py')
_spec = importlib.util.spec_from_file_location('carpark_backfill_acq_currency_script', _SCRIPT_PATH)
backfill_acq_currency = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill_acq_currency)

TEST_COMPANY_ID = 990005

VIN_CONVERTIBLE = 'TESTACQCUR0000001'
VIN_NO_KURS = 'TESTACQCUR0000002'
assert len(VIN_CONVERTIBLE) == 17
assert len(VIN_NO_KURS) == 17


@pytest.fixture
def require_real_db():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping acquisition-currency backfill DB-backed test'
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
def ron_seed():
    """Seeds two RON-convention vehicles under TEST_COMPANY_ID:

      - 'convertible': acquisition_price=40000 (NET LEI), acquisition_currency='RON',
        acquisition_exchange_rate=5, purchase_vat_rate=19 -> the script must
        convert it to acquisition_price=9520 / purchase_price_net=8000 / EUR
        (40000 net LEI -> 47600 gross LEI -> /5 kurs -> 9520 gross EUR;
        40000/5 = 8000 net EUR).
      - 'no_kurs': same NET LEI price but acquisition_exchange_rate=NULL ->
        the script must leave it alone and report it for manual review
        instead of guessing a rate.

    Yields {'convertible': id, 'no_kurs': id}. Teardown deletes every
    carpark_vehicles row for TEST_COMPANY_ID and asserts zero remain.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping acquisition-currency backfill DB-backed test'
        )

    _delete_seed()  # defensive: clean up any leftover rows from a crashed prior run

    conn = get_db()
    ids = {}
    try:
        cur = get_cursor(conn)
        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, company_id,
                 acquisition_currency, acquisition_price, purchase_price_net,
                 acquisition_exchange_rate, purchase_vat_rate)
            VALUES (%s, %s, %s, %s, %s, 'RON', %s, NULL, %s, %s)
            RETURNING id
        ''', (VIN_CONVERTIBLE, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, 40000, 5, 19))
        ids['convertible'] = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, company_id,
                 acquisition_currency, acquisition_price, purchase_price_net,
                 acquisition_exchange_rate, purchase_vat_rate)
            VALUES (%s, %s, %s, %s, %s, 'RON', %s, NULL, NULL, %s)
            RETURNING id
        ''', (VIN_NO_KURS, 'TestBrand', 'TestModel', 'SH', TEST_COMPANY_ID, 40000, 19))
        ids['no_kurs'] = cur.fetchone()['id']

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


def _fetch(vehicle_id):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('''
            SELECT acquisition_price, purchase_price_net, acquisition_currency
            FROM carpark_vehicles WHERE id = %s
        ''', (vehicle_id,))
        return cur.fetchone()
    finally:
        release_db(conn)


def test_convert_is_idempotent(require_real_db, ron_seed):
    vehicle_id = ron_seed['convertible']

    result = backfill_acq_currency.run(apply=True)
    assert vehicle_id in result['converted']

    row = _fetch(vehicle_id)
    assert float(row['acquisition_price']) == 9520.0
    assert float(row['purchase_price_net']) == 8000.0
    assert row['acquisition_currency'] == 'EUR'

    # Re-run: the guard `WHERE id=%s AND acquisition_currency='RON'` means
    # this row no longer matches the audit query at all on a second pass ->
    # untouched, not re-converted, not double-charged.
    result2 = backfill_acq_currency.run(apply=True)
    assert vehicle_id not in result2['converted']
    assert vehicle_id not in result2['manual_review']

    row2 = _fetch(vehicle_id)
    assert float(row2['acquisition_price']) == 9520.0
    assert float(row2['purchase_price_net']) == 8000.0
    assert row2['acquisition_currency'] == 'EUR'


def test_dry_run_writes_nothing(require_real_db, ron_seed):
    vehicle_id = ron_seed['convertible']
    before = _fetch(vehicle_id)
    assert before['acquisition_currency'] == 'RON'

    result = backfill_acq_currency.run(apply=False)
    assert vehicle_id in result['converted']  # eligible/"would convert", but no write

    after = _fetch(vehicle_id)
    assert after == before


def test_row_without_valid_kurs_is_flagged_not_guessed(require_real_db, ron_seed):
    vehicle_id = ron_seed['no_kurs']
    before = _fetch(vehicle_id)
    assert before['acquisition_currency'] == 'RON'

    result = backfill_acq_currency.run(apply=True)
    assert vehicle_id in result['manual_review']
    assert vehicle_id not in result['converted']

    after = _fetch(vehicle_id)
    assert after == before, 'a row with no valid exchange rate must never be written to'
