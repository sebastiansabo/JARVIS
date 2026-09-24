"""Route tests for buyback lookup/reference endpoints (Task 15):
GET /lookups/options, GET+POST /lookups/crm-clients(/search), and
GET /lookups/carpark-vehicles/search.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py (Task 0) — NOT a `client_as`
helper (see test_routes_records.py's module docstring for why: as_role's
fake users have no real `users`/sincron rows, so the org-lookup inside
_acting_company_id would 403 an 'all'-scope request-supplied company_id for
a synthetic client_as-style user; 'own'-scope routes here force
company_id = current_user.company_id server-side and never hit that path).

These lookups reuse crm.repositories.client_repository.ClientRepository and
carpark.repositories.vehicle_repository.VehicleRepository directly (no HTTP
calls to foi_parcurs/carpark) — the create-client test cleans up the row it
inserts via ClientRepository().delete() so repeated runs don't accumulate
test data in the shared localhost/defaultdb.
"""
import json as _json
import secrets

import pytest

pytestmark = pytest.mark.usefixtures('require_real_db')


def _marker(prefix):
    return f'{prefix}-{secrets.token_hex(4)}'


# ═══════════════════════════════════════════════
# OPTIONS
# ═══════════════════════════════════════════════

def test_options_lookup(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/lookups/options')
    assert r.status_code == 200
    body = r.get_json()
    for key in ('fuel_types', 'transmissions', 'gearboxes', 'vat_statuses',
                'acquisition_types', 'client_types', 'client_sources'):
        assert key in body, f'missing {key!r} in {body!r}'
        assert isinstance(body[key], list) and body[key], f'{key} must be a non-empty list'

    assert {o['value'] for o in body['acquisition_types']} == {'buyback', 'tradein'}
    assert {o['value'] for o in body['client_types']} == {'person', 'company'}
    # Every option is a {value, label} pair.
    for key in ('fuel_types', 'transmissions', 'gearboxes', 'vat_statuses', 'client_sources'):
        for opt in body[key]:
            assert 'value' in opt and 'label' in opt


def test_options_requires_login(client):
    r = client.get('/api/buyback/lookups/options')
    assert r.status_code in (302, 401)


def test_options_denied_without_buyback_permission(client, as_role):
    # A bare 'User' role has no permissions_v2 grants seeded for buyback.
    as_role('User', 1)
    r = client.get('/api/buyback/lookups/options')
    assert r.status_code == 403


# ═══════════════════════════════════════════════
# CRM CLIENT SEARCH
# ═══════════════════════════════════════════════

def test_crm_client_search_reuses_repo(client, as_role):
    as_role('Sales', 1)
    r = client.get('/api/buyback/lookups/crm-clients/search?q=a')
    assert r.status_code == 200
    body = r.get_json()
    assert 'clients' in body and isinstance(body['clients'], list)


def test_crm_client_search_too_short_q_not_500(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/lookups/crm-clients/search?q=a')
    assert r.status_code == 200
    assert r.get_json()['clients'] == []


def test_crm_client_search_missing_q_not_500(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/lookups/crm-clients/search')
    assert r.status_code == 200
    assert r.get_json()['clients'] == []


def test_crm_client_search_finds_created_client(client, as_role):
    from crm.repositories.client_repository import ClientRepository

    as_role('Admin', 1)
    marker = _marker('BuybackLookupSearch')
    create = client.post('/api/buyback/lookups/crm-clients', json={
        'display_name': marker,
        'phone': '+40721000001',
    })
    assert create.status_code == 201, create.get_json()
    created = create.get_json()['client']
    try:
        r = client.get(f'/api/buyback/lookups/crm-clients/search?q={marker}')
        assert r.status_code == 200
        names = {c['display_name'] for c in r.get_json()['clients']}
        assert marker in names
    finally:
        ClientRepository().delete(created['id'])


# ═══════════════════════════════════════════════
# CRM CLIENT CREATE
# ═══════════════════════════════════════════════

def test_create_crm_client_requires_display_name(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/lookups/crm-clients', json={'phone': '+40721000002'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_create_crm_client_requires_valid_phone(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/lookups/crm-clients', json={
        'display_name': _marker('BadPhoneClient'), 'phone': 'not-a-phone',
    })
    assert r.status_code == 400


def test_create_crm_client_missing_body_is_400_not_500(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/lookups/crm-clients')
    assert r.status_code == 400


def test_create_crm_client_valid_sets_buyback_source_flag(client, as_role):
    from crm.repositories.client_repository import ClientRepository

    as_role('Admin', 1)
    marker = _marker('BuybackLookupCreate')
    r = client.post('/api/buyback/lookups/crm-clients', json={
        'display_name': marker,
        'phone': '+40721000003',
        'email': 'buyback-lookup-test@example.com',
    })
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body['success'] is True
    created = body['client']
    try:
        assert created['display_name'] == marker
        flags = created.get('source_flags')
        if isinstance(flags, str):
            flags = _json.loads(flags)
        assert flags and flags.get('buyback') is True
    finally:
        ClientRepository().delete(created['id'])


# ═══════════════════════════════════════════════
# CARPARK VEHICLE SEARCH
# ═══════════════════════════════════════════════

def test_carpark_vehicles_search_returns_shape(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/lookups/carpark-vehicles/search?q=a')
    assert r.status_code == 200
    body = r.get_json()
    assert 'vehicles' in body and isinstance(body['vehicles'], list)


def test_carpark_vehicles_search_no_q_not_500(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/lookups/carpark-vehicles/search')
    assert r.status_code == 200
    assert 'vehicles' in r.get_json()


def test_carpark_vehicles_search_sales_scoped_to_own_company(client, as_role):
    as_role('Sales', 1)
    r = client.get('/api/buyback/lookups/carpark-vehicles/search?q=a')
    assert r.status_code == 200
    body = r.get_json()
    for v in body['vehicles']:
        assert v['company_id'] == 1


def test_carpark_vehicles_search_own_scope_no_company_fails_closed(client, as_role):
    as_role('Sales', None)
    r = client.get('/api/buyback/lookups/carpark-vehicles/search?q=a')
    assert r.status_code == 200
    assert r.get_json()['vehicles'] == []
