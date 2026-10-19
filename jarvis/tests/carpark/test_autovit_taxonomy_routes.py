"""Tests for Task 6 of the Autovit Taxonomy Mapping project: the taxonomy
management routes (GET/sync/upsert), the publish wiring that preloads the
map and blocks on an unmapped REQUIRED dimension, and `_autovit_error_message`.

Auth tests mirror `test_autovit_routes_auth.py`'s `_set_user` pattern (three
monkeypatches: `admin_required`/`api_login_required` read `current_user` from
`core.utils.api_helpers`, `carpark_required`/`carpark_edit_required` read it
from `carpark.routes.vehicles`, and anything the route body itself reads
comes from the routes module's own import). Publish tests mirror
`test_autovit_push.py`'s app/test_client + FakeUser idiom (a Blueprint has no
`test_request_context` of its own).

`_autovit_error_message` is pure — no Flask app/DB needed at all.
"""
import pytest
from unittest.mock import ANY, patch

from flask import Flask

import core.utils.api_helpers as api_helpers
import carpark.routes.vehicles as vehicles_mod
from carpark.connectors.autovit import autovit_bp
import carpark.connectors.autovit.routes as r


# ── Auth (403) paths — mirrors test_autovit_routes_auth.py ─────────────────

class AdminUser:
    is_authenticated = True; id = 1; name = 'Admin'; company_id = 10
    can_access_carpark = True; can_edit_carpark = True
    can_view_carpark_finance = True; can_access_settings = True


class NoSettingsUser:
    # CarPark access, no admin — may read the taxonomy, must not sync/edit it.
    is_authenticated = True; id = 2; name = 'Mgr'; company_id = 10
    can_access_carpark = True; can_edit_carpark = True
    can_view_carpark_finance = True; can_access_settings = False


class NoCarparkUser:
    is_authenticated = True; id = 3; name = 'Other'; company_id = 10
    can_access_carpark = False; can_edit_carpark = False
    can_view_carpark_finance = False; can_access_settings = False


def _set_user(monkeypatch, user):
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(r, 'current_user', user)


@pytest.fixture
def auth_client():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    return app.test_client()


def test_taxonomy_get_requires_carpark(auth_client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    resp = auth_client.get('/autovit/api/taxonomy')
    assert resp.status_code == 403


def test_sync_requires_admin(auth_client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())  # carpark access, no admin
    resp = auth_client.post('/autovit/api/taxonomy/sync', json={'account_id': 1})
    assert resp.status_code == 403


def test_map_upsert_requires_admin(auth_client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    resp = auth_client.put('/autovit/api/taxonomy/map',
                           json={'dimension': 'color', 'source_value': 'gri',
                                 'target_code': 'gray'})
    assert resp.status_code == 403


# ── Positive paths: proper permissions reach the handler ───────────────────

def _no_sources(monkeypatch):
    """Stub the Task 7 distinct-source repo methods to empty — isolates a
    test from the real DB when it only cares about cache/map/dimensions."""
    monkeypatch.setattr(r._taxonomy_repo, 'distinct_source_values',
                        lambda cols: {dim: [] for dim in cols})
    monkeypatch.setattr(r._taxonomy_repo, 'distinct_equipment', lambda: [])
    monkeypatch.setattr(r._taxonomy_repo, 'distinct_models', lambda: [])


def test_taxonomy_get_allows_carpark_user(auth_client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(r._taxonomy_repo, 'get_cache', lambda: [{'dimension': 'make', 'code': 'audi'}])
    monkeypatch.setattr(r._taxonomy_repo, 'get_map',
                        lambda: {'make': {('Audi', None): {'target_code': 'audi', 'target_label': 'Audi'}}})
    _no_sources(monkeypatch)
    resp = auth_client.get('/autovit/api/taxonomy')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['cache'] == [{'dimension': 'make', 'code': 'audi'}]
    # the native get_map() shape keys on a (source_value, make) tuple, which
    # jsonify can't encode as a dict key — it must come back flattened.
    assert data['map'] == [{'dimension': 'make', 'source_value': 'Audi', 'make': None,
                            'target_code': 'audi', 'target_label': 'Audi'}]
    assert data['dimensions']['make']['required'] is True
    assert data['dimensions']['equipment']['required'] is False
    # sources is present (empty here — this test only cares about cache/map).
    assert data['sources']['make'] == []
    assert data['sources']['model'] == []
    assert data['sources']['equipment'] == []


def test_taxonomy_get_sources_includes_target_and_suggestions(auth_client, monkeypatch):
    """Task 7: GET /taxonomy must ALSO return `sources` — per-dimension
    distinct in-use CarPark values, each annotated with its current
    resolved target (fold-aware `taxonomy_map.resolve`, same lookup the
    publish path uses) and top-N auto-suggest candidates
    (`taxonomy_sync.suggest`) — for a seeded fuel_type value and a seeded
    make/model pair."""
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(r._taxonomy_repo, 'get_cache', lambda: [
        {'dimension': 'fuel_type', 'code': 'diesel', 'ro_label': 'Diesel', 'make': None},
        {'dimension': 'make', 'code': 'audi', 'ro_label': 'Audi', 'make': None},
        {'dimension': 'model', 'code': 'a4', 'ro_label': 'A4', 'make': 'audi'},
    ])
    # 'make' resolves (Audi -> audi); fuel_type/model have NO map entry yet
    # -> unmapped ("Nemapat" in the UI) but still carry a ranked suggestion.
    monkeypatch.setattr(r._taxonomy_repo, 'get_map', lambda: {
        'make': {('audi', None): {'target_code': 'audi', 'target_label': 'Audi'}},
    })

    def _fake_distinct_source_values(cols):
        if 'make' in cols:
            return {'make': ['Audi']}
        return {dim: (['Diesel'] if dim == 'fuel_type' else []) for dim in cols}

    monkeypatch.setattr(r._taxonomy_repo, 'distinct_source_values', _fake_distinct_source_values)
    monkeypatch.setattr(r._taxonomy_repo, 'distinct_equipment', lambda: [])
    monkeypatch.setattr(r._taxonomy_repo, 'distinct_models',
                        lambda: [{'make': 'Audi', 'value': 'A4'}])

    resp = auth_client.get('/autovit/api/taxonomy')
    assert resp.status_code == 200
    sources = resp.get_json()['sources']

    fuel_row = next(row for row in sources['fuel_type'] if row['source_value'] == 'Diesel')
    assert fuel_row['target_code'] is None  # unmapped -> "Nemapat" in the UI
    assert fuel_row['suggestions'][0]['target_code'] == 'diesel'

    make_row = next(row for row in sources['make'] if row['source_value'] == 'Audi')
    assert make_row['target_code'] == 'audi'  # already mapped
    assert make_row['suggestions'][0]['target_code'] == 'audi'

    model_row = next(row for row in sources['model'] if row['source_value'] == 'A4')
    assert model_row['make'] == 'Audi'
    assert model_row['resolved_make_code'] == 'audi'  # scopes the model lookup/suggest
    assert model_row['target_code'] is None  # unmapped
    assert model_row['suggestions'][0]['target_code'] == 'a4'


def test_sync_allows_admin_and_replaces_cache(auth_client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(r._repo, 'get', lambda aid: {'id': 1, 'connector_type': 'autovit', 'config': {}})

    class _FakeClient:
        pass

    monkeypatch.setattr(r, '_build_client', lambda conn: _FakeClient())
    monkeypatch.setattr(r.taxonomy_sync, 'pull_taxonomy',
                        lambda client: [{'dimension': 'make', 'code': 'audi'},
                                        {'dimension': 'make', 'code': 'bmw'},
                                        {'dimension': 'fuel_type', 'code': 'petrol'}])
    replaced = {}
    monkeypatch.setattr(r._taxonomy_repo, 'replace_cache', lambda rows: replaced.setdefault('rows', rows))

    resp = auth_client.post('/autovit/api/taxonomy/sync', json={'account_id': 1})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['synced'] == 3
    assert data['by_dimension'] == {'make': 2, 'fuel_type': 1}
    assert len(replaced['rows']) == 3


def test_map_upsert_allows_admin(auth_client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    recorded = {}
    monkeypatch.setattr(r._taxonomy_repo, 'upsert',
                        lambda *a, **k: recorded.update(args=a, kwargs=k))
    resp = auth_client.put('/autovit/api/taxonomy/map',
                           json={'dimension': 'color', 'source_value': 'gri',
                                 'make': None, 'target_code': 'gray',
                                 'target_label': 'Gray'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert recorded['args'] == ('color', 'gri', None, 'gray', 'Gray')
    assert recorded['kwargs']['updated_by'] == 1  # AdminUser.id


# ── Publish wiring: blocks on unmapped REQUIRED dims, reports optional ones ─
#
# Mirrors test_autovit_push.py's app/test_client + FakeUser idiom (Blueprint
# has no test_request_context of its own).

VEHICLE = {"id": 7, "vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq",
           "year_of_manufacture": 2019, "mileage_km": 9, "fuel_type": "diesel",
           "body_type": "suv", "color_exterior": "grey",
           "current_price": 100, "listing_title": "t"}
ACCOUNT = {"id": 1, "connector_type": "autovit",
           "config": {"city_id": 1, "region_id": 1}, "credentials": {}}

# A map that resolves every REQUIRED dimension VEHICLE carries EXCEPT
# `model` — the make-scoped miss this project's controller ruling treats as
# "model unmapped" whenever `make` itself didn't resolve under the exact
# source_value/make key the vehicle needs. Here `make` resolves but `model`
# has no entry at all, so vehicle_to_advert reports "model:Kodiaq" unmapped.
# Map keys are folded (lowercase) — resolve() folds VEHICLE's raw-cased
# brand/model ("Skoda"/"Kodiaq") the same way a DB-backed map already is.
_PARTIAL_MAP = {
    'make': {('skoda', None): {'target_code': 'skoda', 'target_label': 'Skoda'}},
    'fuel_type': {('diesel', None): {'target_code': 'diesel', 'target_label': 'Diesel'}},
    'body_type': {('suv', None): {'target_code': 'suv', 'target_label': 'SUV'}},
    'color': {('grey', None): {'target_code': 'gray', 'target_label': 'Gray'}},
}

# The same map, PLUS the model entry — every REQUIRED dimension resolves —
# used by the optional-unmapped-equipment test, which must NOT 422.
_FULL_MAP = dict(_PARTIAL_MAP, model={('kodiaq', 'skoda'): {'target_code': 'kodiaq', 'target_label': 'Kodiaq'}})


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


@pytest.fixture(autouse=True)
def authenticated_editor(monkeypatch):
    monkeypatch.setattr(vehicles_mod, 'current_user', FakeUser())


@pytest.fixture(autouse=True)
def no_photos_no_verify_no_vin_adopt(monkeypatch):
    """Default the publish side-paths to neutral — same idiom as
    test_autovit_push.py — so these tests exercise only the taxonomy-map
    wiring, not photos/verify/VIN-dedup."""
    monkeypatch.setattr(r._photo_repo, 'urls', lambda vid: [])
    monkeypatch.setattr(r, '_verify_advert',
                        lambda client, aid, sent: {'params_dropped': [], 'photos_remote': None})
    monkeypatch.setattr(r.reconcile_service, 'find_active_advert_by_vin',
                        lambda client, vin, **kw: (None, None))


def test_publish_blocks_unmapped_required_422(client, monkeypatch):
    """`model` has no map entry -> reported unmapped, and `model` is a
    REQUIRED dimension -> 422 before any Autovit call."""
    monkeypatch.setattr(r._taxonomy_repo, 'get_map', lambda: _PARTIAL_MAP)
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=VEHICLE), \
         patch.object(r, "_build_client") as bc:
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 422
        data = resp.get_json()
        assert data['success'] is False
        assert 'model:Kodiaq' in data['unmapped_required']
        assert 'model' in data['error']  # a clear RO message naming the field
        bc.assert_not_called()  # no Autovit call made


def test_publish_reports_unmapped_equipment(client, monkeypatch):
    """Every REQUIRED dimension resolves, but an equipment value doesn't —
    equipment isn't in REQUIRED_DIMENSIONS, so publish proceeds (200) and
    reports the miss instead of blocking it."""
    monkeypatch.setattr(r._taxonomy_repo, 'get_map', lambda: _FULL_MAP)
    vehicle = dict(VEHICLE, equipment_options=["some_unmapped_equip"])
    with patch.object(r._repo, "get", return_value=ACCOUNT), \
         patch.object(r._vehicle_repo, "get_by_id", return_value=vehicle), \
         patch.object(r, "_build_client") as bc, \
         patch.object(r._listing_repo, "get", return_value=None), \
         patch.object(r._listing_repo, "upsert") as upsert:
        bc.return_value.create_advert.return_value = {"id": "9", "url": "http://x/9"}
        resp = client.post('/autovit/api/accounts/1/publish', json={"vehicle_id": 7})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'equipment:some_unmapped_equip' in data['unmapped']
        bc.return_value.create_advert.assert_called_once()  # publish proceeded
        assert 'equipment:some_unmapped_equip' in upsert.call_args.kwargs['last_error']


# ── _autovit_error_message: pure function, no Flask/DB involved ────────────

def test_error_message_parses_params_model():
    msg = r._autovit_error_message(
        '{"error":{"details":{"params.model":"Valoare incorecta"}}}')
    assert 'model' in msg


def test_error_message_parses_live_sample():
    """The exact live rejection body confirmed in the task brief."""
    body = ('{"error":{"type":"AdvertsPostingException",'
            '"message":"Adding the ad failed.",'
            '"details":{"params.model":"Valoare incorecta"}}}')
    msg = r._autovit_error_message(body)
    assert 'model' in msg
    assert 'Valoare incorecta' in msg


def test_error_message_falls_back_without_details():
    msg = r._autovit_error_message(
        '{"error":{"type":"AdvertsPostingException","message":"Adding the ad failed."}}')
    assert 'Adding the ad failed' in msg


def test_error_message_never_raises_on_garbage():
    assert r._autovit_error_message('') != ''
    assert r._autovit_error_message('not json') != ''
    assert r._autovit_error_message('{}') != ''
