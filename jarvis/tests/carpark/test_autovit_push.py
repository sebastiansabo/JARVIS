"""Push-sync tests for the Autovit two-way-sync plan.

Part 1 (Task 6, unchanged below): real-DB integration test for the
carpark_autovit_listings table + AutovitListingRepository. Runs against
localhost/defaultdb via the probe in tests/carpark/conftest.py
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

Part 2 (Task 7, appended at the bottom): pure unit tests for the
AutovitClient push methods (create_advert/update_advert/deactivate_advert/
delete_advert/upload_photos). These mock `_request` directly — no DB, no
network — so they run unconditionally (not gated on REAL_DB_AVAILABLE).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        python -m pytest jarvis/tests/carpark/test_autovit_push.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from carpark.connectors.autovit.client import AutovitClient
from database import get_db, get_cursor, release_db

from .conftest import REAL_DB_AVAILABLE

# Fixed, defensively-cleaned-up VIN for the throwaway vehicle. 17 chars,
# alphanumeric, no I/O/Q (VehicleRepository.create's ISO-3779 VIN check).
_TEST_VIN = "TESTPUSH000000001"


@pytest.fixture(scope="module")
def ensure_table():
    """Idempotently create carpark_autovit_listings if the local DB hasn't
    picked up the schema_incremental.py migration yet — mirrors the exact
    DDL added there. Skips (only the DB-backed tests that request it, via
    the `repo` fixture below) if no local DB is reachable.

    Deliberately NOT autouse: Task 7 added pure-unit AutovitClient tests
    further down this file that mock `_request` and need no DB at all. An
    autouse module-scoped fixture that pytest.skip()s would skip those too
    (skip inside any fixture used — even transitively — by a test skips
    that test), so this is only pulled in by the `repo` fixture, which every
    DB-backed test below already depends on."""
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
def repo(ensure_table):
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


# ─────────────────────────────────────────────────────────────────────────
# Task 7: AutovitClient push methods (create/update/deactivate/delete advert
# + upload_photos). Pure unit tests — `_request` is mocked, no DB/network
# involved, so these run regardless of REAL_DB_AVAILABLE.
# ─────────────────────────────────────────────────────────────────────────

def _client():
    return AutovitClient("https://www.autovit.ro/api/open", "cid", "sec", "u", "p")


def test_create_advert_posts_and_returns_id():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {"id": "7060", "url": "http://a"}
        out = c.create_advert({"title": "x"})
        req.assert_called_once()
        assert req.call_args.args[0] == "POST" and req.call_args.args[1] == "/adverts"
        assert req.call_args.kwargs == {"json": {"title": "x"}}
        assert out["id"] == "7060"


def test_update_advert_puts_to_advert_path_and_returns_body():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {"id": "7060", "status": "active"}
        out = c.update_advert("7060", {"title": "y"})
        req.assert_called_once()
        assert req.call_args.args[0] == "PUT" and req.call_args.args[1] == "/adverts/7060"
        assert req.call_args.kwargs == {"json": {"title": "y"}}
        assert out["status"] == "active"


def test_deactivate_advert_posts_to_deactivate_path():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {"id": "7060", "status": "disabled"}
        out = c.deactivate_advert("7060")
        req.assert_called_once_with("POST", "/adverts/7060/deactivate")
        assert out["status"] == "disabled"


def test_delete_advert_deletes_and_reports_success():
    c = _client()
    with patch.object(c, "_request") as req:
        out = c.delete_advert("7060")
        req.assert_called_once_with("DELETE", "/adverts/7060")
        assert out == {"success": True}


def test_upload_photos_posts_each_image_and_returns_ids():
    c = _client()
    with patch.object(c, "_request") as req:
        resp1, resp2 = MagicMock(), MagicMock()
        resp1.json.return_value = {"id": "img1"}
        resp2.json.return_value = {"id": "img2"}
        req.side_effect = [resp1, resp2]

        out = c.upload_photos([b"photo-bytes-1", b"photo-bytes-2"])

        assert req.call_count == 2
        for call in req.call_args_list:
            assert call.args[0] == "POST" and call.args[1] == "/adverts/images"
            assert "files" in call.kwargs
        assert out == ["img1", "img2"]


def test_upload_photos_returns_none_when_no_images():
    c = _client()
    with patch.object(c, "_request") as req:
        out = c.upload_photos([])
        req.assert_not_called()
        assert out is None
