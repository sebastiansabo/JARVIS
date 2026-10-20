"""Unit tests for `carpark.connectors.autovit.service.republish_vehicle` —
the push core extracted from `publish()` (Task 4). Pure mock-based: no DB,
no network.

Mocking idiom matches test_autovit_push.py: `service.py` calls the shared
helpers/singletons (`_build_client`, `_verify_advert`, `_fill_location_contact`,
the `_listing_repo` singleton, `reconcile_service`) through a *live*
attribute lookup on the `routes` module (`r._build_client(...)`, etc.) rather
than a name-import, specifically so that `patch.object(routes, "...")` /
`monkeypatch.setattr(routes, "...")` still intercepts calls made from inside
service.py — see service.py's module docstring for why. These tests patch
the exact same `routes`-module targets to prove that wiring holds.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from flask import Flask

from carpark.connectors.autovit import routes as r
from carpark.connectors.autovit import service as svc
from carpark.connectors.autovit import autovit_bp
import carpark.routes.vehicles as vehicles_mod

VEHICLE = {"id": 7, "vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq",
           "year_of_manufacture": 2019, "mileage_km": 9, "fuel_type": "diesel",
           "body_type": "suv", "color_exterior": "grey",
           "current_price": 100, "listing_title": "t"}
ACCOUNT = {"id": 1, "connector_type": "autovit",
           "config": {"city_id": 1, "region_id": 1}, "credentials": {}}


def _map_entry(target_code, target_label=None):
    return {'target_code': target_code, 'target_label': target_label or target_code}


def _resolving_map():
    """A taxonomy map that resolves every REQUIRED dimension VEHICLE carries
    (mirrors test_autovit_push.py's `_resolving_taxonomy_map`)."""
    return {
        'make': {('skoda', None): _map_entry('skoda', 'Skoda')},
        'model': {('kodiaq', 'skoda'): _map_entry('kodiaq', 'Kodiaq')},
        'fuel_type': {('diesel', None): _map_entry('diesel')},
        'body_type': {('suv', None): _map_entry('suv')},
        'color': {('grey', None): _map_entry('gray')},
    }


def test_republish_skips_when_required_unmapped():
    """A taxonomy map missing a REQUIRED dim (fuel_type) must short-circuit
    the 422 guard BEFORE any Autovit call — the client is never built."""
    tmap = _resolving_map()
    del tmap['fuel_type']  # drop the only entry resolving VEHICLE's fuel_type

    with patch.object(r, "_build_client") as bc:
        result = svc.republish_vehicle(ACCOUNT, VEHICLE, [], tmap,
                                       dry_run=False, now=datetime.now(timezone.utc))

    assert result['success'] is False
    assert any(u.startswith('fuel_type:') for u in result['unmapped_required'])
    bc.assert_not_called()


def test_republish_pushes_and_stamps_last_published_at():
    """All REQUIRED dims mapped -> the push happens and the listing row is
    upserted with `last_published_at=now` (Task 3) + the result's status."""
    tmap = _resolving_map()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    with patch.object(r, "_build_client") as bc, \
         patch.object(r, "_verify_advert",
                      return_value={'params_dropped': [], 'photos_remote': None}), \
         patch.object(r, "_fill_location_contact"), \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert, \
         patch.object(r.reconcile_service, "find_active_advert_by_vin",
                      return_value=(None, None)):
        bc.return_value.create_advert.return_value = {
            "id": "999", "url": "http://x/999", "status": "unpaid"}

        result = svc.republish_vehicle(ACCOUNT, VEHICLE, [], tmap, dry_run=False, now=now)

    assert result['success'] is True
    assert result['status'] == 'unpaid'
    assert result['external_id'] == '999'
    bc.return_value.create_advert.assert_called_once()
    upsert.assert_called_once_with(7, 1, external_advert_id="999",
                                   external_url="http://x/999", status="unpaid",
                                   last_error=None, last_published_at=now)


def test_republish_surfaces_photos_error_from_caller():
    """A photo-fetch failure the caller (route/sweep) hit BEFORE invoking the
    service is threaded in via `photos_error`: the advert is still created
    (photo failures never block publish) but the failure is NOT swallowed —
    it lands in `last_error` with a `photos:` prefix, `photos_ok` is False,
    and no image collection is attempted (photos list was empty anyway)."""
    tmap = _resolving_map()
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    with patch.object(r, "_build_client") as bc, \
         patch.object(r, "_verify_advert",
                      return_value={'params_dropped': [], 'photos_remote': None}), \
         patch.object(r, "_fill_location_contact"), \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert, \
         patch.object(r.reconcile_service, "find_active_advert_by_vin",
                      return_value=(None, None)):
        bc.return_value.create_advert.return_value = {
            "id": "999", "url": "http://x/999", "status": "unpaid"}

        result = svc.republish_vehicle(ACCOUNT, VEHICLE, [], tmap, dry_run=False,
                                       now=now, photos_error="photo lookup failed: db blip")

    assert result['success'] is True          # advert still created
    assert result['photos_ok'] is False
    assert any(w.startswith('photos:') for w in result['warnings'])
    bc.return_value.create_image_collection.assert_not_called()
    assert 'photos: photo lookup failed: db blip' in upsert.call_args.kwargs['last_error']


# ─────────────────────────────────────────────────────────────────────────
# Route-level coverage of the Important review finding: a DB error from
# `_photo_repo.urls(vehicle_id)` inside publish() must NOT be silently
# downgraded to "no photos, no error" — it must surface as a persisted
# `photos:`-prefixed last_error + photos_ok=False in the response, matching
# the pre-refactor signal. Minimal Flask fixtures mirror test_autovit_push.py.
# ─────────────────────────────────────────────────────────────────────────

class FakeUser:
    def __init__(self, id=1, can_access_carpark=True, can_edit_carpark=True):
        self.id = id
        self.is_authenticated = True
        self.can_access_carpark = can_access_carpark
        self.can_edit_carpark = can_edit_carpark


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_publish_records_photo_lookup_failure_without_swallowing(client, monkeypatch):
    """publish() with a raising `_photo_repo.urls` still creates the advert but
    records the photo-lookup failure (persisted last_error + photos_ok=False) —
    the fix for the route silently swallowing a transient DB blip on the photo
    query (regression guard for the Task 4 review finding)."""
    monkeypatch.setattr(vehicles_mod, 'current_user', FakeUser())
    monkeypatch.setattr(r._taxonomy_repo, 'get_map', _resolving_map)
    monkeypatch.setattr(r._photo_repo, 'urls',
                        lambda vid: (_ for _ in ()).throw(RuntimeError("db blip")))

    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r, "_fill_location_contact"), \
         patch.object(r, "_verify_advert",
                      return_value={'params_dropped': [], 'photos_remote': None}), \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert, \
         patch.object(r.reconcile_service, "find_active_advert_by_vin",
                      return_value=(None, None)):
        bc.return_value.create_advert.return_value = {
            "id": "9", "url": "http://x/9", "status": "unpaid"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

    assert resp.status_code == 200          # advert still created
    data = resp.get_json()
    assert data['success'] is True
    assert data['photos_ok'] is False
    assert any(w.startswith('photos:') for w in data['warnings'])
    assert 'photos:' in (upsert.call_args.kwargs['last_error'] or '')
    assert 'db blip' in upsert.call_args.kwargs['last_error']
