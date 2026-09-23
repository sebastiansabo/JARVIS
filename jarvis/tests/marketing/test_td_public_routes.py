"""Real-DB tests for the public (unauthenticated) test-drive booking HTTP
routes in marketing/routes/td_public.py.

Runs against the real localhost DB (DATABASE_URL, default
postgresql://localhost/defaultdb) via the require_real_db fixture in
conftest.py (skips cleanly when no real DB is available).

We deliberately do NOT import the real Flask app / `app.create_app`: booting
it runs init_db(), which fails on unrelated pre-existing schema drift in this
local DB (a schema_hr view). The route module only needs `current_app` for
Flask request/URL plumbing and `current_app.secret_key` (via the service) for
its signed confirm/cancel tokens, so a MINIMAL throwaway Flask app with ONLY
td_public_bp registered supplies everything the routes need -- this exercises
the real route -> service -> repo -> DB path end to end without booting the
rest of the application.

Determinism:
  - TdSlotService.is_car_free is monkeypatched at the CLASS level -> True, so
    availability never depends on real Foaie de Parcurs / lock data. The
    route module instantiates its own TdBookingService/TdSlotService at
    import time, and TdBookingService.__init__ builds its own inner
    TdSlotService too, so a class-level patch is the only way to cover both.
  - marketing.services.td_booking_service.send_customer_message is
    monkeypatched to capture (not send) email.
  - core.notifications.notify.notify_with_push is monkeypatched to a no-op so
    a confirmed booking's best-effort staff notification has no DB/push side
    effects.
  - A far-future (2099) window + min_lead_minutes=0 keeps every materialized
    slot bookable regardless of when the test runs.

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb):
resolved once via `SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1`.
The car's advisor + the page creator use users id=1 (present in the seed DB).

Teardown deletes: FP rows by the test VIN, bookings before their page
(mkt_td_bookings has plain, non-CASCADE FKs -- see project memory), the pages
themselves, and the throwaway CRM clients (guarded by the td_booking source
flag) created by a successful confirm.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.routes.td_public import td_public_bp  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from marketing.services.td_slot_service import TdSlotService  # noqa: E402
import marketing.services.td_slot_service as slot_mod  # noqa: E402
import marketing.services.td_booking_service as svc_mod  # noqa: E402
from core.approvals.booking_token import make_booking_token  # noqa: E402

repo = TdBookingRepository()

_SECRET = 'test-secret'
_SLUG = 'pub-td-1'
_CLOSED_SLUG = 'pub-td-closed'
_VIN = 'PUBTD0001'
_PHONE = '+40721100010'
_PHONE2 = '+40721100099'
_EMAIL = 'ana-pub@ex.com'
_EMAIL2 = 'bob-pub@ex.com'
_LOGO_DATA_URL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='


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


def _cleanup():
    repo.execute('DELETE FROM foi_de_parcurs WHERE vin=%s', (_VIN,))
    for slug in (_SLUG, _CLOSED_SLUG):
        for pg in repo.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (slug,)):
            repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
            repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))
    repo.execute(
        "DELETE FROM crm_clients WHERE phone IN (%s,%s) "
        "AND source_flags @> '{\"td_booking\": true}'::jsonb", (_PHONE, _PHONE2))
    repo.execute('DELETE FROM fp_vehicles WHERE vin=%s', (_VIN,))


@pytest.fixture
def app(require_real_db, monkeypatch):
    """Minimal Flask app with ONLY td_public_bp registered -- see module
    docstring for why this avoids create_app()/init_db()."""
    _cleanup()
    flask_app = Flask(__name__)
    flask_app.secret_key = _SECRET
    flask_app.register_blueprint(td_public_bp, url_prefix='/api/td')

    monkeypatch.setattr(slot_mod.TdSlotService, 'is_car_free', lambda self, *a, **k: True)
    sent = []
    monkeypatch.setattr(svc_mod, 'send_customer_message',
                        lambda *a, **k: (sent.append(a) or (True, '')))
    monkeypatch.setattr('core.notifications.notify.notify_with_push', lambda *a, **k: [])
    flask_app.config['SENT_EMAILS'] = sent

    yield flask_app
    _cleanup()


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


# Valid legal-field body appended to every well-formed submit: the driving
# licence + both consents are now required (422 otherwise).
_VALID_LEGAL = {'license': 'AB 123456', 'gdpr_consent': True, 'conditions_accepted': True}


@pytest.fixture
def open_page(app):
    company_id = _resolve_company_id()
    p = repo.create_page({'company_id': company_id, 'slug': _SLUG, 'created_by': 1,
                          'status': 'open', 'min_lead_minutes': 0, 'title': 'Test Drive X',
                          'logo_url': _LOGO_DATA_URL})
    repo.add_car(p['id'], vin=_VIN, default_advisor_user_id=1)
    # Seed the fleet row so the public car carries a friendly make/model label
    # + plate (cleaned up by _cleanup's DELETE FROM fp_vehicles WHERE vin=...).
    repo.execute(
        "INSERT INTO fp_vehicles (vin, mark, model, registration_number, fuel_type, document_type) "
        "VALUES (%s, 'MG', 'ZS', 'B-100-XYZ', 'Diesel', 'sales')", (_VIN,))
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')
    TdSlotService().materialize_slots(p['id'])
    return p


def _first_slot(client):
    body = client.get(f'/api/td/pages/{_SLUG}').get_json()
    assert body['slots'], 'expected at least one available slot'
    return body['slots'][0]


# ---- GET /api/td/pages/<slug> ----

def test_get_page_public_no_auth(client, open_page):
    r = client.get(f'/api/td/pages/{_SLUG}')
    assert r.status_code == 200
    body = r.get_json()
    assert 'cars' in body and len(body['cars']) == 1
    assert body['cars'][0]['vin'] == _VIN
    assert 'slots' in body and len(body['slots']) >= 1
    assert body['page']['title'] == 'Test Drive X'
    assert body['page']['logo_url'] == _LOGO_DATA_URL
    assert 'company_name' in body['page']


def test_get_page_logo_url_absent_when_unset(client):
    """A page created without a logo returns logo_url: null (not a KeyError),
    so the FE can render its header without a logo gracefully."""
    company_id = _resolve_company_id()
    p = repo.create_page({'company_id': company_id, 'slug': _CLOSED_SLUG, 'created_by': 1,
                          'status': 'open', 'min_lead_minutes': 0, 'title': 'No Logo'})
    try:
        body = client.get(f'/api/td/pages/{_CLOSED_SLUG}').get_json()
        assert body['page']['logo_url'] is None
    finally:
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_get_page_car_label_plate_and_gdpr(client, open_page):
    """The public car carries a friendly make/model label + plate (from the
    joined fleet row), and the page carries the tenant's GDPR text."""
    company_id = open_page['company_id']
    original = repo.query_one('SELECT gdpr_text FROM companies WHERE id=%s', (company_id,))
    repo.execute('UPDATE companies SET gdpr_text=%s WHERE id=%s', ('Politica GDPR de test', company_id))
    try:
        body = client.get(f'/api/td/pages/{_SLUG}').get_json()
        car = body['cars'][0]
        assert car['label'] == 'MG ZS'
        assert car['plate'] == 'B-100-XYZ'
        assert car['vin'] == _VIN
        assert body['page']['gdpr_text'] == 'Politica GDPR de test'
    finally:
        repo.execute('UPDATE companies SET gdpr_text=%s WHERE id=%s',
                     ((original or {}).get('gdpr_text'), company_id))


def test_get_missing_page_404_not_401(client):
    r = client.get('/api/td/pages/nope')
    assert r.status_code == 404
    assert r.status_code != 401


def test_get_unopened_page_404_not_401(client, app):
    """A draft (not-yet-open) page must 404 like a nonexistent slug -- an
    anonymous visitor should never be able to distinguish the two, and must
    never hit 401 either way."""
    company_id = _resolve_company_id()
    p = repo.create_page({'company_id': company_id, 'slug': _CLOSED_SLUG,
                          'created_by': 1, 'status': 'draft', 'min_lead_minutes': 0})
    try:
        r = client.get(f'/api/td/pages/{_CLOSED_SLUG}')
        assert r.status_code == 404
        assert r.status_code != 401
    finally:
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


# ---- POST /api/td/pages/<slug>/bookings ----

def test_submit_booking_201(client, open_page, app):
    slot = _first_slot(client)
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL,
        **_VALID_LEGAL,
    })
    assert r.status_code == 201
    body = r.get_json()
    assert body['status'] == 'pending_confirm'
    assert 'booking_id' in body
    assert app.config['SENT_EMAILS'], 'expected the confirm email to be "sent"'


def test_submit_stores_extra_answers(client, open_page):
    """A full submit persists the legal fields in extra_answers on the booking."""
    slot = _first_slot(client)
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL,
        'license': 'CJ 998877', 'license_expiry': '2030-05-01',
        'gdpr_consent': True, 'conditions_accepted': True,
    })
    assert r.status_code == 201
    booking = repo.get_booking(r.get_json()['booking_id'])
    ea = booking['extra_answers']
    assert ea['license'] == 'CJ 998877'
    assert ea['license_expiry'] == '2030-05-01'
    assert ea['gdpr_consent'] is True and ea['conditions_accepted'] is True


def test_submit_missing_license_422(client, open_page):
    slot = _first_slot(client)
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL,
        'gdpr_consent': True, 'conditions_accepted': True,
    })
    assert r.status_code == 422
    # Nothing was inserted for that page.
    assert repo.query_all('SELECT id FROM mkt_td_bookings WHERE page_id=%s', (open_page['id'],)) == []


def test_submit_missing_gdpr_consent_422(client, open_page):
    slot = _first_slot(client)
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL,
        'license': 'AB 123456', 'conditions_accepted': True,
    })
    assert r.status_code == 422


def test_submit_missing_conditions_422(client, open_page):
    slot = _first_slot(client)
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL,
        'license': 'AB 123456', 'gdpr_consent': True,
    })
    assert r.status_code == 422


def test_submit_booking_missing_fields_400(client, open_page):
    r = client.post(f'/api/td/pages/{_SLUG}/bookings', json={'name': 'Ana'})
    assert r.status_code == 400


def test_submit_booking_missing_page_404_not_401(client):
    r = client.post('/api/td/pages/nope/bookings', json={
        'slot_id': 1, 'name': 'Ana', 'phone': _PHONE, 'email': _EMAIL, **_VALID_LEGAL,
    })
    assert r.status_code == 404
    assert r.status_code != 401


# ---- POST /api/td/bookings/confirm and /cancel ----

def test_confirm_then_cancel_booking(client, open_page):
    slot = _first_slot(client)
    submit = client.post(f'/api/td/pages/{_SLUG}/bookings', json={
        'slot_id': slot['id'], 'name': 'Bob', 'phone': _PHONE2, 'email': _EMAIL2,
        **_VALID_LEGAL,
    })
    booking_id = submit.get_json()['booking_id']

    confirm_token = make_booking_token(booking_id, 'confirm', _SECRET)
    cr = client.post('/api/td/bookings/confirm', json={'token': confirm_token})
    assert cr.status_code == 200
    assert cr.get_json()['status'] == 'confirmed'

    fp_id = cr.get_json()['fp_id']
    fp = repo.query_one('SELECT * FROM foi_de_parcurs WHERE id=%s', (fp_id,))
    assert fp is not None and fp['status'] == 'PLANNED' and fp['vin'] == _VIN

    cancel_token = make_booking_token(booking_id, 'cancel', _SECRET)
    xr = client.post('/api/td/bookings/cancel', json={'token': cancel_token})
    assert xr.status_code == 200
    assert xr.get_json()['status'] == 'cancelled'
    assert repo.query_one('SELECT id FROM foi_de_parcurs WHERE id=%s', (fp_id,)) is None


def test_confirm_bad_token_410_not_401(client):
    r = client.post('/api/td/bookings/confirm', json={'token': 'garbage'})
    assert r.status_code == 410
    assert r.status_code != 401


def test_cancel_bad_token_410_not_401(client):
    r = client.post('/api/td/bookings/cancel', json={'token': 'garbage'})
    assert r.status_code == 410
    assert r.status_code != 401
