# jarvis/tests/carpark/test_publishing_schedule_autocreate.py
"""Task 7: a successful publish (either platform) must auto-create a
`carpark_listing_schedules` row (cadence='1h', enabled=True) when none
exists yet for (vehicle_id, platform_type) — otherwise "auto-update on by
default" is a no-op, since a schedule row today only appears when a user
explicitly picks a cadence.

Mock-based, no DB, no network — mirrors the existing route-test idioms:
  - Shopify: test_shopify_routes.py's `_auth`/`client` fixtures + the
    `test_publish_vehicle_calls_connector` monkeypatch recipe.
  - Autovit: test_autovit_push.py's `app`/`client`/`FakeUser` fixtures +
    the `test_publish_creates_new_listing_and_upserts` monkeypatch recipe.

The shared helper under test is `carpark.connectors.cadence.ensure_auto_schedule`
— these tests patch its module-level `_schedule_repo` (a
ListingScheduleRepository instance) directly, so both platform routes are
exercised against the exact same mocked repo the helper itself calls.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_publishing_schedule_autocreate.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import ANY, patch

import pytest
from flask import Flask

import carpark.connectors.cadence as cadence_mod

# ─────────────────────────────────────────────────────────────────────────
# Shopify
# ─────────────────────────────────────────────────────────────────────────

import core.utils.api_helpers as api_helpers
from carpark.connectors.shopify import shopify_bp
import carpark.connectors.shopify.routes as shopify_routes


class _ShopifyUser:
    is_authenticated = True
    id = 1
    company_id = 10
    can_access_carpark = True
    can_edit_carpark = True
    can_access_settings = True


@pytest.fixture(autouse=True)
def _shopify_auth(monkeypatch):
    user = _ShopifyUser()
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(shopify_routes, 'current_user', user)
    monkeypatch.setattr(shopify_routes._schema_repo, 'seed_defaults_if_empty', lambda: None)


@pytest.fixture
def shopify_client():
    app = Flask(__name__)
    app.register_blueprint(shopify_bp)
    app.config['TESTING'] = True
    return app.test_client()


def _stub_successful_shopify_publish(monkeypatch):
    monkeypatch.setattr(shopify_routes._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(shopify_routes._vehicle_repo, 'get_by_id',
        lambda vid: {'id': vid, 'vin': 'WBA1234567890XYZ1', 'brand': 'BMW',
                     'status': 'LISTED', 'current_price': 45000,
                     'vehicle_type': 'Autoturism'})
    monkeypatch.setattr(shopify_routes._photo_repo, 'get_by_vehicle',
        lambda vid, photo_type=None: [{'url': 'https://cdn/1.jpg',
                                        'is_primary': True, 'sort_order': 0}])
    monkeypatch.setattr(shopify_routes._taxo_repo, 'get_map', lambda: {})
    monkeypatch.setattr(shopify_routes._schema_repo, 'get_active_field_map',
                        lambda: [{'target_key': 'marca'}])
    monkeypatch.setattr(shopify_routes._schema_repo, 'get_value_map', lambda: {})
    monkeypatch.setattr(shopify_routes, '_reconcile_best_effort', lambda client: None)
    monkeypatch.setattr(shopify_routes, 'ensure_platform', lambda pub, dom: 3)

    class FakeConn:
        def __init__(self, *a, **k):
            pass

        def publish(self, v, p, field_map, value_map, config):
            return {'success': True, 'external_id': 'gid://shopify/Product/9',
                    'external_url': 'https://x', 'warnings': []}

    monkeypatch.setattr(shopify_routes, 'ShopifyConnector', FakeConn)


def test_shopify_publish_creates_auto_schedule(shopify_client, monkeypatch):
    """No existing schedule row for (vehicle, 'shopify') → publish upserts
    a '1h' enabled row."""
    _stub_successful_shopify_publish(monkeypatch)
    with patch.object(cadence_mod._schedule_repo, 'get', return_value=None), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as upsert:
        resp = shopify_client.post('/shopify/api/vehicles/7/publish')

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        upsert.assert_called_once_with(7, 'shopify', '1h', True, ANY)


def test_publish_does_not_override_existing_manual(shopify_client, monkeypatch):
    """An existing row — even 'manual' — must be left untouched: this is how
    a user's explicit Manual choice survives a later re-publish."""
    _stub_successful_shopify_publish(monkeypatch)
    existing_manual_row = {'id': 1, 'vehicle_id': 7, 'platform_type': 'shopify',
                           'cadence': 'manual', 'enabled': True, 'next_run_at': None}
    with patch.object(cadence_mod._schedule_repo, 'get', return_value=existing_manual_row), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as upsert:
        resp = shopify_client.post('/shopify/api/vehicles/7/publish')

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        upsert.assert_not_called()


def test_shopify_publish_succeeds_even_if_auto_schedule_raises(shopify_client, monkeypatch):
    """A successful publish must stay a success even when the best-effort
    ensure_auto_schedule() call blows up (e.g. a transient DB error on its
    get-then-upsert) — the ad is already live on Shopify by this point, so
    the route must not turn that into a 500/failure response."""
    _stub_successful_shopify_publish(monkeypatch)
    with patch.object(cadence_mod._schedule_repo, 'get', side_effect=RuntimeError('db blip')):
        resp = shopify_client.post('/shopify/api/vehicles/7/publish')

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


# ─────────────────────────────────────────────────────────────────────────
# Autovit
# ─────────────────────────────────────────────────────────────────────────

from carpark.connectors.autovit import autovit_bp
import carpark.connectors.autovit.routes as autovit_routes
import carpark.routes.vehicles as vehicles_mod

_AUTOVIT_VEHICLE = {"id": 7, "vin": "TMBJK7NS0K8000001", "brand": "Skoda",
                    "model": "Kodiaq", "year_of_manufacture": 2019, "mileage_km": 9,
                    "fuel_type": "diesel", "body_type": "suv", "color_exterior": "grey",
                    "current_price": 100, "listing_title": "t"}
_AUTOVIT_ACCOUNT = {"id": 1, "connector_type": "autovit",
                    "config": {"city_id": 1, "region_id": 1}, "credentials": {}}


class _AutovitUser:
    def __init__(self):
        self.id = 1
        self.is_authenticated = True
        self.can_access_carpark = True
        self.can_edit_carpark = True


@pytest.fixture(autouse=True)
def _autovit_auth(monkeypatch):
    monkeypatch.setattr(vehicles_mod, 'current_user', _AutovitUser())
    # Same literal map used by test_autovit_push.py: resolves every dimension
    # _AUTOVIT_VEHICLE carries, so publish doesn't 422 on unmapped taxonomy.
    monkeypatch.setattr(autovit_routes._taxonomy_repo, 'get_map', lambda: {
        'make': {('skoda', None): {'target_code': 'skoda', 'target_label': 'Skoda'}},
        'model': {('kodiaq', 'skoda'): {'target_code': 'kodiaq', 'target_label': 'Kodiaq'}},
        'fuel_type': {('diesel', None): {'target_code': 'diesel', 'target_label': 'diesel'}},
        'body_type': {('suv', None): {'target_code': 'suv', 'target_label': 'suv'}},
        'color': {('grey', None): {'target_code': 'gray', 'target_label': 'gray'}},
    })
    monkeypatch.setattr(autovit_routes._photo_repo, 'urls', lambda vid: [])
    monkeypatch.setattr(autovit_routes, '_verify_advert',
                        lambda client, aid, sent: {'params_dropped': [], 'photos_remote': None})
    monkeypatch.setattr(autovit_routes.reconcile_service, 'find_active_advert_by_vin',
                        lambda client, vin, **kw: (None, None))


@pytest.fixture
def autovit_client():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_autovit_publish_creates_auto_schedule(autovit_client, monkeypatch):
    """A successful Autovit publish (new advert, create path) also auto-
    creates a '1h' schedule row when none exists yet."""
    with patch.object(autovit_routes._repo, "get", return_value=_AUTOVIT_ACCOUNT), \
         patch.object(autovit_routes._vehicle_repo, "get_by_id", return_value=_AUTOVIT_VEHICLE), \
         patch.object(autovit_routes, "_build_client") as bc, \
         patch.object(autovit_routes._listing_repo, "get", return_value=None), \
         patch.object(autovit_routes._listing_repo, "upsert"), \
         patch.object(cadence_mod._schedule_repo, 'get', return_value=None), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as schedule_upsert:
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}

        resp = autovit_client.post('/autovit/api/accounts/1/publish',
                                    json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        schedule_upsert.assert_called_once_with(7, 'autovit', '1h', True, ANY)


def test_autovit_publish_succeeds_even_if_auto_schedule_raises(autovit_client, monkeypatch):
    """Same best-effort guarantee on the Autovit side: the advert is already
    created by the time ensure_auto_schedule() runs, so a DB error there must
    not downgrade the response to a failure."""
    with patch.object(autovit_routes._repo, "get", return_value=_AUTOVIT_ACCOUNT), \
         patch.object(autovit_routes._vehicle_repo, "get_by_id", return_value=_AUTOVIT_VEHICLE), \
         patch.object(autovit_routes, "_build_client") as bc, \
         patch.object(autovit_routes._listing_repo, "get", return_value=None), \
         patch.object(autovit_routes._listing_repo, "upsert"), \
         patch.object(cadence_mod._schedule_repo, 'get', side_effect=RuntimeError('db blip')):
        bc.return_value.create_advert.return_value = {"id": "999", "url": "http://x/999"}

        resp = autovit_client.post('/autovit/api/accounts/1/publish',
                                    json={"vehicle_id": 7})

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
