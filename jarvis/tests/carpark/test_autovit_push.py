"""Real-DB integration test for the Autovit push-sync repository
(carpark_autovit_listings + AutovitListingRepository, Task 6 of the Autovit
two-way-sync plan).

Runs against localhost/defaultdb via the probe in tests/carpark/conftest.py
(REAL_DB_AVAILABLE), the same idiom used by test_dispo_repository_sql.py.

Deviations from the task-6 brief's sample test:

1. FK-safety: carpark_autovit_listings.vehicle_id REFERENCES
   carpark_vehicles(id) and account_id REFERENCES connectors(id) (both
   ON DELETE CASCADE). The brief's snippet upserts with a hardcoded
   vehicle_id=999999 / account_id=20, which fails the vehicle FK the moment
   the table exists with constraints enabled (id 999999 doesn't exist in
   carpark_vehicles). This test instead creates a throwaway carpark_vehicles
   row (valid 17-char VIN, no I/O/Q per the ISO-3779 check in
   VehicleRepository.create) to get a real vehicle id, and resolves a real
   account id via `SELECT id FROM connectors WHERE connector_type='autovit'
   LIMIT 1` — skipping if none is seeded locally. Both the listing row and
   the throwaway vehicle are deleted in a `finally` block.

2. Table existence: schema_incremental.py's new
   `CREATE TABLE IF NOT EXISTS carpark_autovit_listings` only runs through
   the app's init_db() path, which this narrow repository test doesn't
   invoke. The module-scoped `ensure_table` fixture below issues the exact
   same idempotent DDL directly against localhost/defaultdb before any test
   runs, and asserts the table exists via information_schema afterward.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python -m pytest jarvis/tests/carpark/test_autovit_push.py -v
"""
import pytest

from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from database import get_db, get_cursor, release_db

from .conftest import REAL_DB_AVAILABLE

# Fixed, defensively-cleaned-up VIN for the throwaway vehicle. 17 chars,
# alphanumeric, no I/O/Q (VehicleRepository.create's ISO-3779 VIN check).
_TEST_VIN = "TESTPUSH000000001"


@pytest.fixture(scope="module", autouse=True)
def ensure_table():
    """Idempotently create carpark_autovit_listings if the local DB hasn't
    picked up the schema_incremental.py migration yet — mirrors the exact
    DDL added there. Skips the whole module if no local DB is reachable."""
    if not REAL_DB_AVAILABLE:
        pytest.skip("no local DB")
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS carpark_autovit_listings (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER NOT NULL REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
                account_id INTEGER NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
                external_advert_id TEXT,
                external_url TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                last_sync TIMESTAMP,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (vehicle_id, account_id)
            )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_carpark_autovit_listings_vehicle '
                    'ON carpark_autovit_listings(vehicle_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_carpark_autovit_listings_account '
                    'ON carpark_autovit_listings(account_id)')
        conn.commit()

        cur.execute('''
            SELECT EXISTS (SELECT FROM information_schema.tables
                           WHERE table_schema='public' AND table_name='carpark_autovit_listings')
        ''')
        assert cur.fetchone()['exists'] is True, \
            "carpark_autovit_listings was not created in localhost/defaultdb"
    finally:
        release_db(conn)


@pytest.fixture
def repo():
    if not REAL_DB_AVAILABLE:
        pytest.skip("no local DB")
    return AutovitListingRepository()


@pytest.fixture
def listing_seed():
    """Create a throwaway carpark_vehicles row + resolve a real autovit
    connector account id. Tears both down (plus any listing row created
    mid-test) in a finally block."""
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id FROM connectors WHERE connector_type = 'autovit' LIMIT 1")
        account_row = cur.fetchone()
        if not account_row:
            pytest.skip("no autovit connector account seeded locally")
        account_id = account_row["id"]

        # Defensive: clean up a leftover row from a previously crashed run.
        cur.execute("DELETE FROM carpark_vehicles WHERE vin = %s", (_TEST_VIN,))

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model)
            VALUES (%s, %s, %s) RETURNING id
        ''', (_TEST_VIN, "TestBrand", "TestModel"))
        vehicle_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        release_db(conn)

    try:
        yield {"vehicle_id": vehicle_id, "account_id": account_id}
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute(
                "DELETE FROM carpark_autovit_listings WHERE vehicle_id = %s AND account_id = %s",
                (vehicle_id, account_id))
            cur.execute("DELETE FROM carpark_vehicles WHERE id = %s", (vehicle_id,))
            conn.commit()
        finally:
            release_db(conn)


def test_upsert_roundtrip(repo, listing_seed):
    vehicle_id = listing_seed["vehicle_id"]
    account_id = listing_seed["account_id"]

    repo.upsert(vehicle_id=vehicle_id, account_id=account_id, external_advert_id="AB1",
                external_url="http://x", status="active")
    row = repo.get(vehicle_id, account_id)
    assert row["external_advert_id"] == "AB1" and row["status"] == "active"

    repo.upsert(vehicle_id=vehicle_id, account_id=account_id, status="inactive")
    updated = repo.get(vehicle_id, account_id)
    assert updated["status"] == "inactive"
    # a partial upsert (only `status` given) must not clobber fields it didn't touch
    assert updated["external_advert_id"] == "AB1"
    assert updated["external_url"] == "http://x"


def test_set_error_sets_status_and_message(repo, listing_seed):
    vehicle_id = listing_seed["vehicle_id"]
    account_id = listing_seed["account_id"]

    repo.set_error(vehicle_id, account_id, "rejected: missing photos")
    row = repo.get(vehicle_id, account_id)
    assert row["status"] == "error"
    assert row["last_error"] == "rejected: missing photos"


def test_get_returns_none_when_no_listing_exists(repo, listing_seed):
    # listing_seed only creates the vehicle/account pair; no listing row yet.
    assert repo.get(listing_seed["vehicle_id"], listing_seed["account_id"]) is None
