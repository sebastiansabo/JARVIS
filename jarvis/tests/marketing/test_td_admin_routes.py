"""Real-DB tests for the authenticated staff admin HTTP routes in
marketing/routes/td_admin.py (attached to marketing_bp -> /marketing/api/td/...).

Runs against the real localhost DB (DATABASE_URL, default
postgresql://localhost/defaultdb) via the require_real_db fixture in
tests/marketing/conftest.py (skips cleanly when no real DB is available).

Auth harness: these routes are gated `@login_required` (flask_login) and read
`current_user.id`. We deliberately do NOT use `app.create_app()` -- booting it
runs init_db(), which fails on unrelated pre-existing schema drift in this
local DB (a schema_hr view; see project memory). Instead we build a MINIMAL
Flask app, register the real `marketing_bp` (importing `marketing` attaches
every marketing route module, including td_admin, onto that one blueprint --
verified import-safe standalone the same way tests/marketing/conftest.py's
real-DB probe already proves for the rest of the marketing package), and
satisfy flask_login with a tiny stub LoginManager + user_loader instead of a
real users/permissions round trip. A session cookie logs in seeded user id=1
before every request, matching how `td_public` public-route tests avoid
create_app() for the same reason.

`marketing_bp` carries no url_prefix itself (app.py supplies '/marketing' at
registration: `flask_app.register_blueprint(marketing_bp,
url_prefix='/marketing')`) -- this test replicates that exact prefix so URLs
match the spec's `/marketing/api/td/...` paths.

Determinism: a far-future (2099) booking window keeps materialize_slots'
output independent of when the test runs. company_id is resolved from the
seed DB (not hardcoded) the same way test_td_public_routes.py does.

Teardown deletes bookings before their page (mkt_td_bookings has plain,
non-CASCADE FKs -- see project memory), the pages themselves, and any
foi_de_parcurs row created for the reassign-advisor test.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from flask import Flask  # noqa: E402
from flask_login import LoginManager  # noqa: E402

from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()

_SECRET = 'test-secret'
_SLUG = 'adm-td-1'
_VIN = 'ADMTD0001'
_VIN2 = 'ADMTD0002'
_USER1_ID = 1


class _StubUser:
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __init__(self, user_id):
        self.id = user_id

    def get_id(self):
        return str(self.id)


def _resolve_company_id():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    return row['id']


def _resolve_second_user_id():
    """A users.id != 1, present in the seed DB, to reassign a booking's
    advisor to (so the reassignment is a real change, not a no-op)."""
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM users WHERE id <> %s ORDER BY id LIMIT 1', (_USER1_ID,))
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'need a second seed user to test advisor reassignment'
    return row['id']


def _user_name(user_id):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT name FROM users WHERE id=%s', (user_id,))
        row = cur.fetchone()
    finally:
        release_db(conn)
    return row['name'] if row else None


def _cleanup():
    repo.execute('DELETE FROM foi_de_parcurs WHERE vin IN (%s,%s)', (_VIN, _VIN2))
    for pg in repo.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (_SLUG,)):
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))


@pytest.fixture
def app(require_real_db):
    """Minimal Flask app with the real marketing_bp (td_admin included)
    registered under the same '/marketing' prefix app.py uses, plus a stub
    LoginManager so @login_required is satisfiable without a real auth
    round trip. See module docstring for why create_app() is avoided."""
    _cleanup()

    # Imported here (not module-level) so the require_real_db skip can fire
    # before pulling in the whole marketing package.
    from marketing import marketing_bp

    flask_app = Flask(__name__)
    flask_app.secret_key = _SECRET

    lm = LoginManager()
    lm.init_app(flask_app)

    @lm.user_loader
    def _load_user(user_id):
        return _StubUser(int(user_id))

    flask_app.register_blueprint(marketing_bp, url_prefix='/marketing')

    yield flask_app
    _cleanup()


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_user_id'] = str(_USER1_ID)
        yield c


@pytest.fixture
def company_id(app):
    return _resolve_company_id()


# ---- create page -> add car -> add window -> materialize ----

def test_create_page_add_car_window_materialize(client, company_id):
    r = client.post('/marketing/api/td/pages',
                     json={'company_id': company_id, 'slug': _SLUG, 'title': 'Admin TD'})
    assert r.status_code == 201
    page = r.get_json()
    pid = page['id']
    assert page['slug'] == _SLUG
    assert page['status'] == 'draft'

    car_r = client.post(f'/marketing/api/td/pages/{pid}/cars',
                         json={'vin': _VIN, 'default_advisor_user_id': _USER1_ID})
    assert car_r.status_code == 201
    assert car_r.get_json()['vin'] == _VIN

    win_r = client.post(f'/marketing/api/td/pages/{pid}/windows',
                         json={'window_date': '2099-10-01', 'start_time': '10:00', 'end_time': '11:00'})
    assert win_r.status_code == 201

    m = client.post(f'/marketing/api/td/pages/{pid}/materialize')
    assert m.status_code == 200
    inserted = m.get_json()['inserted']
    assert inserted > 0

    # materialize is idempotent (bulk_insert_slots no-ops on conflict)
    m2 = client.post(f'/marketing/api/td/pages/{pid}/materialize')
    assert m2.get_json()['inserted'] == 0


def test_missing_required_fields_400(client, company_id):
    r = client.post('/marketing/api/td/pages', json={'title': 'no slug or company'})
    assert r.status_code == 400

    page = client.post('/marketing/api/td/pages',
                        json={'company_id': company_id, 'slug': _SLUG}).get_json()
    r2 = client.post(f'/marketing/api/td/pages/{page["id"]}/cars', json={})
    assert r2.status_code == 400


# ---- list pages / bookings ----

def test_list_pages_and_bookings(client, company_id):
    r = client.post('/marketing/api/td/pages',
                     json={'company_id': company_id, 'slug': _SLUG, 'title': 'Admin TD'})
    pid = r.get_json()['id']

    pages = client.get(f'/marketing/api/td/pages?company_id={company_id}')
    assert pages.status_code == 200
    assert any(p['id'] == pid for p in pages.get_json()['pages'])

    bookings = client.get(f'/marketing/api/td/pages/{pid}/bookings')
    assert bookings.status_code == 200
    assert bookings.get_json()['bookings'] == []


# ---- status transition ----

def test_set_status(client, company_id):
    r = client.post('/marketing/api/td/pages',
                     json={'company_id': company_id, 'slug': _SLUG})
    pid = r.get_json()['id']

    ok = client.post(f'/marketing/api/td/pages/{pid}/status', json={'status': 'open'})
    assert ok.status_code == 200
    assert ok.get_json()['status'] == 'open'

    bad = client.post(f'/marketing/api/td/pages/{pid}/status', json={'status': 'bogus'})
    assert bad.status_code == 400


# ---- reassign advisor: booking + advisor_user_id + FP advisor_name sync ----

def test_reassign_advisor_syncs_fp_advisor_name(client, company_id):
    new_advisor_id = _resolve_second_user_id()
    new_advisor_name = _user_name(new_advisor_id)
    assert new_advisor_name, 'second seed user has no name to assert against'

    page = repo.create_page({'company_id': company_id, 'slug': _SLUG, 'created_by': _USER1_ID,
                              'status': 'open', 'min_lead_minutes': 0, 'title': 'Reassign test'})
    car = repo.add_car(page['id'], vin=_VIN2, default_advisor_user_id=_USER1_ID)
    repo.add_window(page['id'], '2099-10-02', '09:00', '10:00')
    slots = repo.list_open_slots(page['id'])
    if not slots:
        from marketing.services.td_slot_service import TdSlotService
        TdSlotService().materialize_slots(page['id'])
        slots = repo.list_open_slots(page['id'])
    assert slots, 'expected at least one materialized slot'
    slot = slots[0]

    # Minimal PLANNED foi_de_parcurs row, linked to the booking, so the
    # reassignment has a real FP row to sync advisor_name onto.
    fp = repo.execute(
        "INSERT INTO foi_de_parcurs (contract_id, vin, company_id, route_type, "
        "km_start, km_end, distance_km, fuel_tank_capacity_liters, "
        "fuel_gauge_start_level, fuel_gauge_end_level, fuel_start_liters, "
        "fuel_end_liters, fuel_consumed_liters, status, advisor_name) "
        "VALUES (%s,%s,%s,'TD',0,0,0,0,'1/1','1/1',0,0,0,'PLANNED',%s) RETURNING *",
        (f'ADM-TD-TEST-{_VIN2}', _VIN2, company_id, 'Original Advisor'), returning=True)

    booking = repo.create_booking({
        'page_id': page['id'], 'slot_id': slot['id'], 'car_id': car['id'],
        'customer_name': 'Test Customer', 'customer_phone_e164': '+40721000001',
        'customer_email': 'reassign@ex.com', 'advisor_user_id': _USER1_ID,
        'expires_at': '2099-10-02 08:00:00+00',
    })
    repo.mark_confirmed(booking['id'], None, fp['id'], _USER1_ID)

    r = client.patch(f'/marketing/api/td/bookings/{booking["id"]}/advisor',
                      json={'advisor_user_id': new_advisor_id})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True

    updated_booking = repo.get_booking(booking['id'])
    assert updated_booking['advisor_user_id'] == new_advisor_id

    updated_fp = repo.query_one('SELECT advisor_name FROM foi_de_parcurs WHERE id=%s', (fp['id'],))
    assert updated_fp['advisor_name'] == new_advisor_name


def test_reassign_advisor_missing_booking_404(client):
    r = client.patch('/marketing/api/td/bookings/999999999/advisor',
                      json={'advisor_user_id': 1})
    assert r.status_code == 404


def test_reassign_advisor_missing_field_400(client, company_id):
    page = repo.create_page({'company_id': company_id, 'slug': _SLUG, 'created_by': _USER1_ID})
    car = repo.add_car(page['id'], vin=_VIN2)
    repo.add_window(page['id'], '2099-10-03', '09:00', '10:00')
    from marketing.services.td_slot_service import TdSlotService
    TdSlotService().materialize_slots(page['id'])
    slot = repo.list_open_slots(page['id'])[0]
    booking = repo.create_booking({
        'page_id': page['id'], 'slot_id': slot['id'], 'car_id': car['id'],
        'customer_name': 'X', 'customer_phone_e164': '+40721000002',
        'customer_email': 'x@ex.com', 'expires_at': '2099-10-03 08:00:00+00',
    })
    r = client.patch(f'/marketing/api/td/bookings/{booking["id"]}/advisor', json={})
    assert r.status_code == 400
