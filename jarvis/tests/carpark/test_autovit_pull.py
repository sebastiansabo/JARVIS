"""Tests for the Autovit pull-import upsert (carpark/connectors/autovit/routes.py
import_advert): "Autovit wins" — UPDATE only taxonomy.MERGE_FIELDS when a VIN
already exists in carpark_vehicles, else CREATE.

Mock-based, mirroring tests/carpark/test_dispo_routes.py /
test_documents_routes.py: a minimal Flask app registers autovit_bp so
`request.get_json()` resolves inside a real request context (Blueprint has
no `test_request_context` of its own, unlike a Flask app), and `current_user`
is monkeypatched directly onto every module that reads it at call time.

Deviation from the task-2 brief's sample test: the brief's snippet calls
`r.autovit_bp.test_request_context(...)` and invokes `r.import_advert(1)`
directly. Flask's Blueprint has no `test_request_context` method (only Flask
app objects do), and even if it did, `@api_login_required` (core/utils/
api_helpers.py) checks a module-level `current_user.is_authenticated` that
would reject an anonymous context with a 401 — making the test fail for the
wrong reason. So this file instead: (1) builds a real Flask app + test
client, and (2) monkeypatches `current_user` to an authenticated stand-in in
both `core.utils.api_helpers` (where `@api_login_required` reads it) and
`carpark.connectors.autovit.routes` (where `import_advert` reads it for
created_by/updated_by) — the same "patch every module namespace that
imported current_user" idiom already used by test_dispo_routes.py. No
production code (the decorator) is weakened; only the real flask_login
`current_user` proxy is swapped out for the test.
"""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from carpark.connectors.autovit import routes as r
from carpark.connectors.autovit import autovit_bp
import core.utils.api_helpers as api_helpers_mod

ADVERT = {"title": "Skoda Kodiaq", "params": {
    "vin": "TMBJK7NS0K8000001", "make": "skoda", "model": "kodiaq",
    "year": 2019, "mileage": 90000, "fuel_type": "diesel", "gearbox": "automatic",
    "price": {"1": 17000, "currency": "EUR"}}}


class FakeUser:
    def __init__(self, id=1):
        self.id = id
        self.is_authenticated = True


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def authenticated_user(monkeypatch):
    """@api_login_required reads current_user from core.utils.api_helpers'
    namespace; import_advert reads it from its own module namespace. Both
    must be patched for the handler to run past the auth gate."""
    user = FakeUser()
    monkeypatch.setattr(api_helpers_mod, 'current_user', user)
    monkeypatch.setattr(r, 'current_user', user)


def test_import_updates_existing_only_merge_fields(client):
    existing = {"id": 7, "vin": "TMBJK7NS0K8000001",
                "acquisition_price": 12000, "current_price": 15000}
    with patch.object(r, "_build_client") as bc, \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=existing), \
         patch.object(r._vehicle_repo, "update", return_value={**existing, "id": 7}) as upd, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._photo_repo, "count", return_value=0):
        bc.return_value.get_advert.return_value = ADVERT
        resp = client.post('/autovit/api/accounts/1/import-advert', json={"advert_id": "1"})

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['action'] == 'updated'
        assert body['photo_added'] == 0        # ADVERT fixture has no photos key

        written = upd.call_args.args[1]
        assert "acquisition_price" not in written          # internal untouched
        assert written["current_price"] == 17000            # Autovit wins
        assert written["brand"] == "Skoda"
        assert set(written) <= r.taxonomy.MERGE_FIELDS


def test_import_creates_new_vehicle_when_vin_not_found(client):
    created = {"id": 42, "vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq"}
    with patch.object(r, "_build_client") as bc, \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=None), \
         patch.object(r._vehicle_repo, "create", return_value=created) as create, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._photo_repo, "count", return_value=0):
        bc.return_value.get_advert.return_value = ADVERT
        resp = client.post('/autovit/api/accounts/1/import-advert', json={"advert_id": "1"})

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['action'] == 'created'
        assert body['vehicle']['id'] == 42
        assert body['photo_added'] == 0        # ADVERT fixture has no photos key

        written = create.call_args.args[0]
        assert written['vin'] == "TMBJK7NS0K8000001"
        assert written['created_by'] == 1
        assert written['updated_by'] == 1


# ── Photo fallback (Task 3): _maybe_import_photos ──
#
# Autovit "photos" shape: {"<index>": {"<WxH>": "<url>", ...}, ...} — a dict
# keyed by photo index, each value a dict of size-variant URLs keyed by
# "WIDTHxHEIGHT". The fallback only runs when the vehicle has zero existing
# photos (never overwrites curated photos), always picks the largest-width
# variant per photo, and marks the first inserted photo as primary.

def test_photos_added_only_when_none():
    advert = {"photos": {"1": {"2048x1360": "https://cdn/x/big.jpg",
                               "732x488": "https://cdn/x/small.jpg"}}}
    with patch("carpark.connectors.autovit.routes._photo_repo") as pr:
        pr.count.return_value = 0
        n = r._maybe_import_photos(MagicMock(), advert, vehicle_id=7)
        assert n == 1
        url = pr.add.call_args.kwargs["url"]
        assert url == "https://cdn/x/big.jpg"           # largest size
        assert pr.add.call_args.kwargs["is_primary"] is True


def test_photos_skipped_when_present():
    with patch("carpark.connectors.autovit.routes._photo_repo") as pr:
        pr.count.return_value = 3
        assert r._maybe_import_photos(MagicMock(), {"photos": {}}, 7) == 0
        pr.add.assert_not_called()


def test_photos_multiple_only_first_is_primary():
    advert = {"photos": {
        "1": {"2048x1360": "https://cdn/x/1-big.jpg", "732x488": "https://cdn/x/1-small.jpg"},
        "2": {"2048x1360": "https://cdn/x/2-big.jpg"},
    }}
    with patch("carpark.connectors.autovit.routes._photo_repo") as pr:
        pr.count.return_value = 0
        n = r._maybe_import_photos(MagicMock(), advert, vehicle_id=9)
        assert n == 2
        calls = pr.add.call_args_list
        assert calls[0].kwargs["is_primary"] is True
        assert calls[0].kwargs["photo_type"] == "autovit"
        assert calls[1].kwargs["is_primary"] is False


# ── Bulk import-all (Task 4) ──
#
# POST /accounts/<id>/import-all paginates every "active" page via
# client.get_adverts(page=, status='active'), upserts each advert by VIN
# (same taxonomy.advert_to_vehicle + MERGE_FIELDS rules as import_advert),
# and returns an aggregate summary. Per-advert failures must not abort the
# batch — they're collected into `errors` and the loop continues.

def test_import_all_paginates_and_summarizes(client):
    page1 = {"results": [ADVERT, {"params": {"make": "audi", "model": "a4"}}],
             "total_pages": 2, "current_page": 1}
    page2 = {"results": [{**ADVERT, "params": {**ADVERT["params"],
                          "vin": "WAUZZZ8K0AA000002", "make": "audi", "model": "a4"}}],
             "total_pages": 2, "current_page": 2}
    with patch.object(r, "_build_client") as bc, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._repo, "add_sync_log") as log, \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=None), \
         patch.object(r._vehicle_repo, "create", side_effect=lambda d: {"id": 1}), \
         patch.object(r, "_maybe_import_photos", return_value=0):
        bc.return_value.get_adverts.side_effect = [page1, page2]
        resp = client.post('/autovit/api/accounts/1/import-all')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['imported'] == 2
        assert body['updated'] == 0
        assert body['skipped_no_vin'] == 1
        assert body['photo_added'] == 0
        assert body['errors'] == []
        # both pages were fetched (loop paginates until page > total_pages)
        assert bc.return_value.get_adverts.call_count == 2
        log.assert_called_once()


def test_import_all_collects_per_advert_errors_and_continues(client):
    """A single advert blowing up (e.g. vehicle_repo.create raising) must not
    abort the batch — it's recorded in `errors` and the remaining adverts in
    the page still get processed."""
    good_advert = {**ADVERT, "id": "2"}
    bad_advert = {**ADVERT, "id": "1",
                  "params": {**ADVERT["params"], "vin": "WAUZZZ8K0AA000099"}}
    page1 = {"results": [bad_advert, good_advert], "total_pages": 1, "current_page": 1}

    def create_side_effect(d):
        if d.get("vin") == "WAUZZZ8K0AA000099":
            raise RuntimeError("db exploded")
        return {"id": 5}

    with patch.object(r, "_build_client") as bc, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._repo, "add_sync_log"), \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=None), \
         patch.object(r._vehicle_repo, "create", side_effect=create_side_effect), \
         patch.object(r, "_maybe_import_photos", return_value=0):
        bc.return_value.get_advert.side_effect = lambda aid: (
            bad_advert if aid == "1" else good_advert)
        bc.return_value.get_adverts.return_value = page1
        resp = client.post('/autovit/api/accounts/1/import-all')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['imported'] == 1
        assert len(body['errors']) == 1
        assert body['errors'][0]['advert_id'] == "1"
        assert 'db exploded' in body['errors'][0]['error']


def test_import_all_page_fetch_failure_returns_partial_progress(client):
    """A page-fetch failure mid-pagination must NOT 500 and must NOT lose the
    progress already made on earlier pages: page 1 imports succeed, the page-2
    fetch error is recorded in `errors` (advert_id=None), pagination stops, and
    the accumulated summary is returned with 200/success=True."""
    page1 = {"results": [ADVERT], "total_pages": 2, "current_page": 1}
    with patch.object(r, "_build_client") as bc, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._repo, "add_sync_log") as log, \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=None), \
         patch.object(r._vehicle_repo, "create", side_effect=lambda d: {"id": 1}), \
         patch.object(r, "_maybe_import_photos", return_value=0):
        bc.return_value.get_adverts.side_effect = [page1, RuntimeError("boom")]
        resp = client.post('/autovit/api/accounts/1/import-all')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['imported'] == 1                      # page 1's success survived
        assert len(body['errors']) == 1
        assert body['errors'][0]['advert_id'] is None
        assert 'page 2 fetch failed' in body['errors'][0]['error']
        assert 'boom' in body['errors'][0]['error']
        # both pages were attempted, then pagination stopped
        assert bc.return_value.get_adverts.call_count == 2
        # sync log still written, marked 'partial' because errors were collected
        log.assert_called_once()
        assert log.call_args.args[2] == 'partial'


def test_import_all_client_build_failure_returns_502(client):
    """If the client can't even be built (bad creds, ...), fail fast with 502
    before any pagination — no sync log, no partial summary."""
    with patch.object(r, "_build_client", side_effect=RuntimeError("bad creds")) as bc, \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._repo, "add_sync_log") as log:
        resp = client.post('/autovit/api/accounts/1/import-all')

        assert resp.status_code == 502
        body = resp.get_json()
        assert body['success'] is False
        assert 'bad creds' in body['error']
        log.assert_not_called()


def test_import_succeeds_when_photo_import_raises(client):
    """Photos are a best-effort side effect: a photo-layer DB error must NOT
    turn an already-successful vehicle upsert into a 500. import_advert should
    still return success with photo_added == 0."""
    created = {"id": 55, "vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq"}
    with patch.object(r, "_build_client") as bc, \
         patch.object(r._vehicle_repo, "get_by_vin", return_value=None), \
         patch.object(r._vehicle_repo, "create", return_value=created), \
         patch.object(r._repo, "get", return_value={"id": 1, "connector_type": "autovit",
                                                    "config": {}, "credentials": {}}), \
         patch.object(r._photo_repo, "count", side_effect=RuntimeError("db down")):
        bc.return_value.get_advert.return_value = ADVERT
        resp = client.post('/autovit/api/accounts/1/import-advert', json={"advert_id": "1"})

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['action'] == 'created'
        assert body['vehicle']['id'] == 55
        assert body['photo_added'] == 0        # photo failure swallowed
