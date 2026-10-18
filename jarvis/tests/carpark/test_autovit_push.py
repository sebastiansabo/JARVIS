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
from unittest.mock import ANY, MagicMock, patch

from flask import Flask

from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from carpark.connectors.autovit.client import AutovitClient
from carpark.connectors.autovit import routes as r
from carpark.connectors.autovit import autovit_bp
import carpark.routes.vehicles as vehicles_mod
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
        assert req.call_args.args[0] == "POST" and req.call_args.args[1] == "/account/adverts"
        assert req.call_args.kwargs == {"json": {"title": "x"}}
        assert out["id"] == "7060"


def test_update_advert_puts_to_advert_path_and_returns_body():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {"id": "7060", "status": "active"}
        out = c.update_advert("7060", {"title": "y"})
        req.assert_called_once()
        assert req.call_args.args[0] == "PUT" and req.call_args.args[1] == "/account/adverts/7060"
        assert req.call_args.kwargs == {"json": {"title": "y"}}
        assert out["status"] == "active"


def test_deactivate_advert_posts_to_deactivate_path():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.json.return_value = {"id": "7060", "status": "disabled"}
        out = c.deactivate_advert("7060")
        req.assert_called_once_with("POST", "/account/adverts/7060/deactivate", json={})
        assert out["status"] == "disabled"


def test_delete_advert_deletes_and_reports_success():
    c = _client()
    with patch.object(c, "_request") as req:
        out = c.delete_advert("7060")
        req.assert_called_once_with("DELETE", "/account/adverts/7060")
        assert out == {"success": True}


def test_create_image_collection_posts_numeric_keyed_and_returns_id():
    c = _client()
    with patch.object(c, "_request") as req:
        req.return_value.ok = True
        req.return_value.json.return_value = {"id": "821"}

        out = c.create_image_collection(["http://img/1.jpg", "http://img/2.jpg"])

        req.assert_called_once()
        assert req.call_args.args == ("POST", "/imageCollections")
        # Autovit's body is a flat 1-indexed map of position -> URL string, with
        # NO "images" wrapper and NO {"source": url} nesting — any non-numeric key
        # returns 400 "All keys must be numbers".
        assert req.call_args.kwargs["json"] == {
            "1": "http://img/1.jpg", "2": "http://img/2.jpg"}
        assert out == "821"


def test_create_image_collection_returns_none_when_no_images():
    c = _client()
    with patch.object(c, "_request") as req:
        assert c.create_image_collection([]) is None
        req.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Task 8: publish / unpublish routes. Same mock-based idiom as
# test_autovit_pull.py: a minimal Flask app registers autovit_bp so
# `request.get_json()` resolves inside a real request context (Blueprint has
# no `test_request_context` of its own), `LOGIN_DISABLED=True` makes
# flask_login's `@login_required` a no-op, and `current_user` is
# monkeypatched onto carpark.routes.vehicles (where @carpark_edit_required —
# the mutating-route auth+permission gate, replacing the former bare
# `@api_login_required` — reads it).
#
# Deviation from the task-8 brief's Step-1 sample test: the brief calls
# `r.autovit_bp.test_request_context(...)` + `r.publish(1)` directly, which
# doesn't work for the same reasons documented at the top of
# test_autovit_pull.py (no such method on Blueprint; would reject anyway).
# This uses the app/test_client fixtures instead, per the task-8 brief's own
# "AUTH IN TESTS" instruction to reuse that idiom.
# ─────────────────────────────────────────────────────────────────────────

VEHICLE = {"id": 7, "vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq",
           "year_of_manufacture": 2019, "mileage_km": 9, "fuel_type": "diesel",
           "body_type": "suv", "color_exterior": "grey",
           "current_price": 100, "listing_title": "t"}
ACCOUNT = {"id": 1, "connector_type": "autovit",
           "config": {"city_id": 1, "region_id": 1}, "credentials": {}}


class FakeUser:
    def __init__(self, id=1, can_access_carpark=True, can_edit_carpark=True):
        self.id = id
        self.is_authenticated = True
        self.can_access_carpark = can_access_carpark
        self.can_edit_carpark = can_edit_carpark


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _set_user(monkeypatch, user):
    """@carpark_edit_required reads current_user from carpark.routes.vehicles'
    namespace (where it's defined) — must be patched there for the handler
    to run past the auth+permission gate. publish/unpublish don't read
    current_user themselves (unlike import_advert), so the routes' own
    module namespace doesn't need patching."""
    monkeypatch.setattr(vehicles_mod, 'current_user', user)


_REAL_VERIFY_ADVERT = r._verify_advert  # captured before the autouse stub below
_REAL_FIND_BY_VIN = r.reconcile_service.find_active_advert_by_vin  # autouse stubs the module attr


@pytest.fixture(autouse=True)
def no_photos_no_verify(monkeypatch):
    """Default the publish side-paths to neutral: no photos on the vehicle and
    a post-publish read-back that reports nothing dropped. Tests for those
    paths override explicitly."""
    monkeypatch.setattr(r._photo_repo, 'urls', lambda vid: [])
    monkeypatch.setattr(r, '_verify_advert',
                        lambda client, aid, sent: {'params_dropped': [], 'photos_remote': None})


@pytest.fixture(autouse=True)
def no_vin_adopt(monkeypatch):
    """Default the publish create-path VIN-dedup scan to 'no live ad found', so
    create-path tests create as before. The adopt test overrides this."""
    monkeypatch.setattr(r.reconcile_service, 'find_active_advert_by_vin',
                        lambda client, vin, **kw: (None, None))


@pytest.fixture(autouse=True)
def authenticated_user(monkeypatch):
    """Every test gets an authenticated user with carpark edit permission by
    default; tests that need a different shape override via
    _set_user(monkeypatch, FakeUser(...))."""
    _set_user(monkeypatch, FakeUser())


def test_publish_requires_edit_permission(client, monkeypatch):
    """An authenticated user without can_edit_carpark must be rejected —
    publish pushes the vehicle catalog live to the Autovit marketplace and
    must not be reachable by a viewer with no CarPark edit permission."""
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})
    assert resp.status_code == 403


def test_unpublish_requires_edit_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    resp = client.post('/autovit/api/accounts/1/unpublish', json={"vehicle_id": 7})
    assert resp.status_code == 403


def test_verify_status_requires_edit_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    resp = client.post('/autovit/api/vehicles/7/verify-status', json={})
    assert resp.status_code == 403


def test_verify_status_writes_live_status_to_listing(client, monkeypatch):
    """Verifică status reads the live advert and persists its real status —
    the fix for a paid/active ad still showing as draft (unpaid) in JARVIS."""
    monkeypatch.setattr(r, '_verify_vehicle_ownership', lambda vid: (VEHICLE, None))
    monkeypatch.setattr(r._listing_repo, 'list_by_vehicle',
                        lambda vid: [{'external_advert_id': 'A1', 'account_id': 1,
                                      'external_url': 'http://old', 'status': 'unpaid'}])
    monkeypatch.setattr(r._repo, 'get', lambda aid: ACCOUNT)

    class _FakeClient:
        def get_account_advert(self, advert_id, timeout=None):
            return {'status': 'active', 'url': 'http://live'}

    monkeypatch.setattr(r, '_build_client', lambda conn: _FakeClient())

    recorded = {}

    def _fake_upsert(vehicle_id, account_id, **fields):
        recorded.update(fields, vehicle_id=vehicle_id, account_id=account_id)
        return {}

    monkeypatch.setattr(r._listing_repo, 'upsert', _fake_upsert)

    resp = client.post('/autovit/api/vehicles/7/verify-status', json={})
    assert resp.status_code == 200
    assert resp.get_json()['refreshed'] == 1
    assert recorded['status'] == 'active'
    assert recorded['external_url'] == 'http://live'


def test_publish_account_not_found_returns_404(client):
    with patch.object(r._repo, "get", return_value=None):
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})
        assert resp.status_code == 404
        assert resp.get_json()['success'] is False


def test_publish_vehicle_not_found_returns_404(client):
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=None):
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 999})
        assert resp.status_code == 404


def test_publish_dry_run_returns_payload_without_network(client):
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc:
        resp = client.post('/autovit/api/accounts/1/publish',
                            json={"vehicle_id": 7, "dry_run": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["dry_run"] is True
        assert data["advert"]["params"]["make"] == "skoda"
        bc.assert_not_called()


def test_publish_missing_required_fields_returns_400(client):
    incomplete_vehicle = {"id": 7, "brand": "Skoda"}  # no model/year/mileage/fuel/price/body_type/color
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=incomplete_vehicle), \
         patch.object(r, "_build_client") as bc:
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "params.price" in data["missing"]
        bc.assert_not_called()


def test_publish_creates_new_listing_and_upserts(client):
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["external_id"] == "999"
        bc.return_value.create_advert.assert_called_once()
        bc.return_value.update_advert.assert_not_called()
        upsert.assert_called_once_with(7, 1, external_advert_id="999",
                                       external_url="http://x/999",
                                       status="active", last_error=None)


def test_publish_updates_existing_listing_via_update_advert(client):
    existing = {"external_advert_id": "555", "external_url": "http://x/555"}
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=existing), \
         patch.object(r._listing_repo, "upsert") as upsert:
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        bc.return_value.update_advert.assert_called_once_with("555", ANY)
        bc.return_value.create_advert.assert_not_called()
        upsert.assert_called_once_with(7, 1, external_advert_id="555",
                                       external_url="http://x/555",
                                       status="active", last_error=None)


def test_publish_recreates_when_listing_status_removed(client):
    """A listing whose status is removed_* (ad deleted on Autovit) is re-created,
    not updated — updating a removed advert 400s on Autovit."""
    existing = {"external_advert_id": "555", "external_url": "http://x/555",
                "status": "removed_by_user"}
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=existing), \
         patch.object(r._listing_repo, "upsert"):
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["external_id"] == "999"
        bc.return_value.create_advert.assert_called_once()
        bc.return_value.update_advert.assert_not_called()


def test_publish_falls_back_to_create_when_update_400s(client):
    """If Autovit 400s an update (advert gone), publish recreates instead of
    surfacing a server error."""
    import requests
    existing = {"external_advert_id": "555", "external_url": "http://x/555", "status": "active"}
    err = requests.HTTPError()
    err.response = type("R", (), {"status_code": 400})()
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=existing), \
         patch.object(r._listing_repo, "upsert"):
        bc.return_value.update_advert.side_effect = err
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["external_id"] == "999"
        bc.return_value.update_advert.assert_called_once()
        bc.return_value.create_advert.assert_called_once()


def test_publish_adopts_live_advert_by_vin_instead_of_creating(client, monkeypatch):
    """No local link, but a live Autovit ad with the same VIN exists → adopt +
    update it (connect/reconcile), NOT create a duplicate."""
    monkeypatch.setattr(r.reconcile_service, "find_active_advert_by_vin",
                        lambda client, vin, **kw: ("555", "http://x/555"))
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["external_id"] == "555"
        assert data["updated_existing"] is True
        assert any("deja publicat" in w.lower() for w in data.get("warnings", []))
        bc.return_value.update_advert.assert_called_once_with("555", ANY)
        bc.return_value.create_advert.assert_not_called()
        # The listing is connected to the adopted advert.
        assert upsert.call_args.kwargs["external_advert_id"] == "555"


def test_publish_creates_when_no_live_vin_match(client):
    """No local link and no live same-VIN ad → create a new advert."""
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert"):
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["external_id"] == "999"
        bc.return_value.create_advert.assert_called_once()


def test_publish_warns_already_published_without_polluting_last_error(client):
    # Re-publishing a car that already has an advert updates it in place and
    # surfaces an informational "already published" warning in the response —
    # but that note must NOT be written to last_error (reserved for real faults).
    existing = {"external_advert_id": "555", "external_url": "http://x/555"}
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client"), \
         patch.object(r._listing_repo, "get", return_value=existing), \
         patch.object(r._listing_repo, "upsert") as upsert:
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['updated_existing'] is True
        assert any('deja publicat' in w.lower() for w in body['warnings'])
        # last_error stays None — the informational note is not a fault
        assert upsert.call_args.kwargs['last_error'] is None


def test_publish_creates_as_unpaid_draft_without_forcing_status(client):
    # Autovit creates every new advert in `unpaid` status (a private draft, not
    # visible on the marketplace) on its own — so we do NOT inject a bogus
    # `status` into the create payload, and the listing row records the real
    # status the API returns.
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_advert.return_value = {"id": "1", "url": "http://x", "status": "unpaid"}
        resp = client.post('/autovit/api/accounts/1/publish',
                            json={"vehicle_id": 7, "draft": True})

        assert resp.status_code == 200
        sent_advert = bc.return_value.create_advert.call_args.args[0]
        assert "status" not in sent_advert
        assert upsert.call_args.kwargs["status"] == "unpaid"


def test_publish_error_sets_listing_error_and_returns_502(client):
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "set_error") as set_error:
        bc.return_value.create_advert.side_effect = RuntimeError("autovit rejected")
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 502
        data = resp.get_json()
        assert data["success"] is False
        assert "autovit rejected" in data["error"]
        set_error.assert_called_once_with(7, 1, "autovit rejected")


def test_unpublish_success(client):
    listing = {"external_advert_id": "555"}
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._listing_repo, "get", return_value=listing), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "upsert") as upsert:
        resp = client.post('/autovit/api/accounts/1/unpublish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        bc.return_value.deactivate_advert.assert_called_once_with("555")
        upsert.assert_called_once_with(7, 1, status='inactive')


def test_unpublish_no_listing_returns_404(client):
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._listing_repo, "get", return_value=None):
        resp = client.post('/autovit/api/accounts/1/unpublish', json={"vehicle_id": 7})
        assert resp.status_code == 404


def test_unpublish_error_returns_502(client):
    listing = {"external_advert_id": "555"}
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._listing_repo, "get", return_value=listing), \
         patch.object(r, "_build_client") as bc:
        bc.return_value.deactivate_advert.side_effect = RuntimeError("boom")
        resp = client.post('/autovit/api/accounts/1/unpublish', json={"vehicle_id": 7})

        assert resp.status_code == 502
        assert resp.get_json()["success"] is False


# ─────────────────────────────────────────────────────────────────────────
# Photos + post-publish verification (2026-10-15 fix: photos and several
# params never reached Autovit; the failure was swallowed as a log warning).
# ─────────────────────────────────────────────────────────────────────────

from carpark.connectors.autovit import taxonomy as taxo
from carpark.services import photo_urls as pu


def test_public_photo_urls_presigns_private_keys_and_passes_http_through(monkeypatch):
    monkeypatch.setattr(pu.spaces_service, 'presigned_url',
                        lambda key, expires=0: f'https://signed/{key}?ttl={expires}')
    out = pu.public_photo_urls(['private/carpark/7/a.jpg', 'https://cdn/x.jpg', '', 'data:image/png;base64,AA'])
    assert out == ['https://signed/private/carpark/7/a.jpg?ttl=86400',
                   'https://cdn/x.jpg', 'data:image/png;base64,AA']


def test_publish_presigns_photo_keys_before_image_collection(client, monkeypatch):
    monkeypatch.setattr(r._photo_repo, 'urls',
                        lambda vid: ['private/carpark/7/1.jpg', 'private/carpark/7/2.jpg'])
    monkeypatch.setattr(pu.spaces_service, 'presigned_url',
                        lambda key, expires=0: f'https://signed/{key}')
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_image_collection.return_value = 'ic-1'
        bc.return_value.create_advert.return_value = {"id": "9", "url": "http://x/9"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        bc.return_value.create_image_collection.assert_called_once_with(
            ['https://signed/private/carpark/7/1.jpg', 'https://signed/private/carpark/7/2.jpg'])
        sent = bc.return_value.create_advert.call_args.args[0]
        assert sent['image_collection_id'] == 'ic-1'
        data = resp.get_json()
        assert data['photos_sent'] == 2 and data['photos_ok'] is True
        assert upsert.call_args.kwargs['last_error'] is None


def test_publish_records_photo_failure_without_blocking_advert(client, monkeypatch):
    monkeypatch.setattr(r._photo_repo, 'urls', lambda vid: ['https://cdn/1.jpg'])
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_image_collection.side_effect = RuntimeError("400 bad source")
        bc.return_value.create_advert.return_value = {"id": "9", "url": "http://x/9"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200          # advert still created
        data = resp.get_json()
        assert data['success'] is True
        assert data['photos_ok'] is False
        assert any(w.startswith('photos:') for w in data['warnings'])
        sent = bc.return_value.create_advert.call_args.args[0]
        assert 'image_collection_id' not in sent
        assert '400 bad source' in upsert.call_args.kwargs['last_error']


def test_publish_reports_params_dropped_by_autovit(client, monkeypatch):
    monkeypatch.setattr(r, '_verify_advert', _REAL_VERIFY_ADVERT)
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_advert.return_value = {"id": "9", "url": "http://x/9"}
        # Autovit kept everything except body_type and color.
        bc.return_value.get_account_advert.return_value = {
            "id": "9", "params": {"vin": "x", "make": "skoda", "model": "kodiaq",
                                  "year": 2019, "mileage": 9, "fuel_type": "diesel",
                                  "price": {}, "is_imported_car": "0"},
            "photos": [{"1": "a"}]}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        data = resp.get_json()
        assert data['params_dropped'] == ['body_type', 'color']
        assert data['photos_remote'] == 1
        assert 'params_dropped: body_type, color' in upsert.call_args.kwargs['last_error']


def test_verify_advert_never_raises():
    c = MagicMock()
    c.get_account_advert.side_effect = RuntimeError("boom")
    assert r._verify_advert(c, "1", {"params": {"a": 1}}) == {'params_dropped': [], 'photos_remote': None}
    assert r._verify_advert(c, None, {}) == {'params_dropped': [], 'photos_remote': None}


def test_vehicle_to_advert_emits_euro_and_origin_but_not_date_registration():
    from datetime import date
    v = dict(VEHICLE, first_registration_date=date(2018, 3, 8),
             euro_standard="Euro 6", country_of_origin="DE")
    p = taxo.vehicle_to_advert(v, ACCOUNT)["params"]
    # date_registration is dropped — Autovit 400s on its (unconfirmed) format.
    assert "date_registration" not in p
    # euro_standard label is normalised to the Autovit slug before sending
    # (raw "Euro 6" was silently dropped by Autovit → blank "Norma de poluare").
    assert p["pollution_standard"] == "euro-6"
    assert p["country_origin"] == "DE"


def test_vehicle_to_advert_never_emits_date_registration():
    """date_registration is never sent (Autovit rejects the format), whatever the
    first_registration_date value is."""
    for val in ("2018-03-08", "n/a", None):
        p = taxo.vehicle_to_advert(dict(VEHICLE, first_registration_date=val), ACCOUNT)["params"]
        assert "date_registration" not in p
    p = taxo.vehicle_to_advert(VEHICLE, ACCOUNT)["params"]
    assert "pollution_standard" not in p and "country_origin" not in p


# ── find_active_advert_by_vin (publish VIN-dedup scan) ──

def test_find_active_advert_by_vin_matches_and_early_exits():
    seen_pages = []

    class FakeClient:
        def get_adverts(self, page=1, status=None, timeout=None):
            seen_pages.append(page)
            if page == 1:
                return {"total_pages": 3, "results": [
                    {"id": 1, "url": "u1", "params": {"vin": "WAUZZZ111"}},
                    {"id": 2, "url": "u2", "params": {"vin": "  wauzzz222 "}}]}
            return {"total_pages": 3, "results": []}

        def get_advert(self, advert_id, timeout=None):
            return {}

    assert _REAL_FIND_BY_VIN(FakeClient(), "WAUZZZ222") == ("2", "u2")
    assert seen_pages == [1]  # early-exit: never paged past the match


def test_find_active_advert_by_vin_no_match_returns_none():
    class FakeClient:
        def get_adverts(self, page=1, status=None, timeout=None):
            return {"total_pages": 1, "results": [{"id": 9, "url": "u9", "params": {"vin": "OTHER"}}]}

        def get_advert(self, advert_id, timeout=None):
            return {}

    assert _REAL_FIND_BY_VIN(FakeClient(), "TARGET") == (None, None)


def test_find_active_advert_by_vin_falls_back_to_get_advert_when_list_lacks_vin():
    """When the list payload omits VIN, it does a bounded get_advert per advert."""
    detail_ids = []

    class FakeClient:
        def get_adverts(self, page=1, status=None, timeout=None):
            return {"total_pages": 1, "results": [{"id": 10, "url": "u10"}, {"id": 11, "url": "u11"}]}

        def get_advert(self, advert_id, timeout=None):
            detail_ids.append(advert_id)
            return {"params": {"vin": "FOUND" if advert_id == "11" else "NOPE"}}

    assert _REAL_FIND_BY_VIN(FakeClient(), "found") == ("11", "u11")
    assert detail_ids == ["10", "11"]  # detail lookup per VIN-less advert, in order


def test_find_active_advert_by_vin_caps_detail_lookups():
    """`detail_cap` bounds how many get_advert fallbacks fire (504 guard)."""
    calls = []

    class FakeClient:
        def get_adverts(self, page=1, status=None, timeout=None):
            return {"total_pages": 1, "results": [{"id": i} for i in range(10)]}

        def get_advert(self, advert_id, timeout=None):
            calls.append(advert_id)
            return {}  # never carries a VIN → never matches

    assert _REAL_FIND_BY_VIN(FakeClient(), "x", detail_cap=2) == (None, None)
    assert len(calls) == 2  # capped at detail_cap
