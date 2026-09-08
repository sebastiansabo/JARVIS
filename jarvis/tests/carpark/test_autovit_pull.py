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
