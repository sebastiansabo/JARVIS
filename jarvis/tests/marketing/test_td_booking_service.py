"""Real-DB tests for TdBookingService — the submit / confirm / cancel orchestration
that wires the public test-drive booking flow together.

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb)
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).
Imports the REAL psycopg2 (not the process-wide mock installed for the rest of the suite)
so the atomic confirm's transaction / advisory lock / RETURNING behaviour is genuine.

We do NOT import the real Flask app / create_app: booting it runs init_db(), which can
fail on unrelated pre-existing schema drift in this local DB (a schema_hr view). The
service only needs current_app.secret_key for its signed tokens, so a MINIMAL throwaway
Flask app supplies the app context.

Determinism:
  - svc.slots.is_car_free is monkeypatched -> True so availability never depends on real
    Foaie de Parcurs / lock data; a FAR-FUTURE window (2099) + min_lead_minutes=0 keeps
    every materialized slot bookable.
  - td_booking_service.send_customer_message is monkeypatched to capture (not send) email.
  - core.notifications.notify.notify_with_push is monkeypatched to a no-op so a confirmed
    booking's best-effort staff notification has no DB/push side effects.

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): resolved once via
`SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1`. The car's advisor + the
page creator use users id=1 (present in the seed DB). Teardown deletes the FP rows by the
test VIN, the bookings before the page (mkt_td_bookings has plain, non-CASCADE FKs), the
throwaway CRM clients (guarded by the td_booking source flag), and any fp_vehicles seed.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
import psycopg2  # noqa: E402  (real driver, bound by conftest's require_real_db probe)
from datetime import datetime, timezone  # noqa: E402
from flask import Flask, current_app  # noqa: E402

import marketing.services.td_booking_service as svc_mod  # noqa: E402
from marketing.services.td_booking_service import TdBookingService  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from core.approvals.booking_token import make_booking_token  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402

repo = TdBookingRepository()

_SLUG = 'svc-td-1'
_VIN = 'SVC00001'
_PHONE = '+40721000010'
_PHONE2 = '+40721000011'
_EMAIL = 'ana-svc@ex.com'
_EMAIL2 = 'bob-svc@ex.com'


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


def _cleanup(page_id=None):
    repo.execute("DELETE FROM foi_de_parcurs WHERE vin=%s", (_VIN,))
    if page_id is not None:
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (page_id,))
    for pg in repo.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (_SLUG,)):
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))
    repo.execute("DELETE FROM crm_clients WHERE phone IN (%s,%s) "
                 "AND source_flags @> '{\"td_booking\": true}'::jsonb", (_PHONE, _PHONE2))
    repo.execute('DELETE FROM fp_vehicles WHERE vin=%s', (_VIN,))


@pytest.fixture
def open_page(require_real_db, monkeypatch):
    _cleanup()
    p = repo.create_page({'company_id': _resolve_company_id(), 'slug': _SLUG,
                          'created_by': 1, 'status': 'open', 'min_lead_minutes': 0})
    c = repo.add_car(p['id'], vin=_VIN, default_advisor_user_id=1)
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')

    svc = TdBookingService()
    svc.slots.materialize_slots(p['id'])
    # Deterministic availability, captured email, silent staff-notify.
    monkeypatch.setattr(svc.slots, 'is_car_free', lambda *a, **k: True)
    sent = []
    monkeypatch.setattr(svc_mod, 'send_customer_message',
                        lambda *a, **k: (sent.append(a) or (True, '')))
    monkeypatch.setattr('core.notifications.notify.notify_with_push',
                        lambda *a, **k: [])

    app = Flask(__name__)
    app.secret_key = 'test-secret'
    with app.app_context():
        yield svc, p, c, sent
    _cleanup(p['id'])


def _first_slot(svc, page):
    slots = svc.slots.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert slots, 'expected at least one available slot'
    return slots[0]


def test_submit_sends_email(open_page):
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL,
                           {}, '1.2.3.4', 'ua', 'https://x')
    assert r.success and r.status_code == 201
    assert r.data['status'] == 'pending_confirm'
    assert len(sent) == 1


def test_double_submit_one_conflict(open_page):
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r1 = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.1.1.1', 'ua', 'x')
    r2 = svc.submit_booking(_SLUG, slot['id'], 'Bob', _PHONE2, _EMAIL2, {}, '2.2.2.2', 'ua', 'x')
    assert r1.status_code == 201
    assert r2.status_code == 409


def test_confirm_creates_planned_fp(open_page):
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.2.3.4', 'ua', 'x')
    booking_id = r.data['booking_id']

    token = make_booking_token(booking_id, 'confirm', current_app.secret_key)
    cr = svc.confirm_booking(token)
    assert cr.success and cr.status_code == 200 and cr.data['status'] == 'confirmed'

    fp = repo.query_one('SELECT * FROM foi_de_parcurs WHERE id=%s', (cr.data['fp_id'],))
    assert fp is not None and fp['route_type'] == 'TD' and fp['status'] == 'PLANNED'
    assert fp['vin'] == _VIN and fp['contract_id'] == f'TDB-{booking_id}'

    b = repo.get_booking(booking_id)
    assert b['status'] == 'confirmed' and b['foi_de_parcurs_id'] == cr.data['fp_id']


def test_cancel_deletes_planned_fp_and_frees_slot(open_page):
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.2.3.4', 'ua', 'x')
    booking_id = r.data['booking_id']
    cr = svc.confirm_booking(make_booking_token(booking_id, 'confirm', current_app.secret_key))
    fp_id = cr.data['fp_id']

    xr = svc.cancel_booking(make_booking_token(booking_id, 'cancel', current_app.secret_key))
    assert xr.success and xr.status_code == 200 and xr.data['status'] == 'cancelled'

    assert repo.get_booking(booking_id)['status'] == 'cancelled'
    assert repo.query_one('SELECT id FROM foi_de_parcurs WHERE id=%s', (fp_id,)) is None
    # The slot is bookable again (cancelled bookings don't hold it).
    free_ids = {s['id'] for s in svc.slots.available_slots(
        p['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))}
    assert slot['id'] in free_ids
