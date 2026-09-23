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
from core.approvals.booking_token import make_booking_token, make_group_token  # noqa: E402
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
    # 10:00-12:00 @ 30min = four slots (10:00, 10:30, 11:00, 11:30). The multi-
    # interval group tests pick NON-adjacent slots (e.g. 10:00 + 11:00) so the two
    # confirmed fișe don't collide on their shared boundary (back-to-back TD
    # sessions on the same VIN legitimately conflict at confirm).
    repo.add_window(p['id'], '2099-10-01', '10:00', '12:00')

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


def _two_nonadjacent_slots(svc, page):
    """First + third available slot (10:00 and 11:00) — leaving a gap so two
    confirmed TD fișe on the same VIN don't collide on a shared boundary."""
    slots = svc.slots.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert len(slots) >= 3, 'expected at least three available slots for the group tests'
    return slots[0], slots[2]


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


def test_submit_normalizes_e164_phone(open_page):
    """A phone with spaces is normalized to canonical E.164 before it is stored /
    used for dedup (spec §7)."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', '+40 721 000 111', _EMAIL,
                           {}, '1.2.3.4', 'ua', 'x')
    assert r.success and r.status_code == 201
    b = repo.get_booking(r.data['booking_id'])
    assert b['customer_phone_e164'] == '+40721000111'


def test_submit_rejects_non_e164_phone(open_page):
    """A phone without a country code (not E.164) is rejected 422 and stored nowhere."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', '0721000111', _EMAIL,
                           {}, '1.2.3.4', 'ua', 'x')
    assert not r.success and r.status_code == 422
    # Nothing was inserted for that page.
    assert repo.query_all('SELECT id FROM mkt_td_bookings WHERE page_id=%s', (p['id'],)) == []


def test_submit_filters_utm_allowlist(open_page):
    """Only the tracked utm_* keys are persisted; unknown keys are dropped (spec §7)."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(
        _SLUG, slot['id'], 'Ana', _PHONE, _EMAIL,
        {'utm_source': 'fb', 'utm_medium': 'cpc', 'evil': 'drop-me', 'ref': 'x'},
        '1.2.3.4', 'ua', 'x')
    assert r.success and r.status_code == 201
    stored = repo.get_booking(r.data['booking_id'])['utm']
    assert stored == {'utm_source': 'fb', 'utm_medium': 'cpc'}


def test_double_confirm_idempotent(open_page):
    """Two sequential confirm calls with the same token: the first confirms; the
    second is idempotent success (200, confirmed) — the good booking is NOT flipped
    to 'conflict', its slot stays held, and the PLANNED FP row is still present."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.2.3.4', 'ua', 'x')
    booking_id = r.data['booking_id']
    token = make_booking_token(booking_id, 'confirm', current_app.secret_key)

    cr1 = svc.confirm_booking(token)
    assert cr1.success and cr1.status_code == 200 and cr1.data['status'] == 'confirmed'
    fp_id = cr1.data['fp_id']

    cr2 = svc.confirm_booking(token)
    assert cr2.success and cr2.status_code == 200 and cr2.data['status'] == 'confirmed'
    assert cr2.data['fp_id'] == fp_id

    b = repo.get_booking(booking_id)
    assert b['status'] == 'confirmed' and b['foi_de_parcurs_id'] == fp_id
    assert repo.query_one('SELECT id FROM foi_de_parcurs WHERE id=%s', (fp_id,)) is not None
    free_ids = {s['id'] for s in svc.slots.available_slots(
        p['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))}
    assert slot['id'] not in free_ids


def test_confirm_race_not_flipped_to_conflict(open_page, monkeypatch):
    """A racing DUPLICATE confirm that read the booking while it was still pending
    (before the first commit) must NOT corrupt the good booking. We force the
    pre-atomic read to hand back a stale 'pending_confirm' snapshot so the flow
    reaches confirm_booking_atomic, whose FOR-UPDATE guard (booking already
    'confirmed') raises TdBookingNotPending. The service must return idempotent
    success and leave the booking 'confirmed' + its slot held + its FP row intact —
    NOT flip it to 'conflict' (which would free the slot) and NOT return 409."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.2.3.4', 'ua', 'x')
    booking_id = r.data['booking_id']
    token = make_booking_token(booking_id, 'confirm', current_app.secret_key)

    cr1 = svc.confirm_booking(token)
    assert cr1.success and cr1.data['status'] == 'confirmed'
    fp_id = cr1.data['fp_id']

    real_get = svc.repo.get_booking
    state = {'n': 0}

    def fake_get(bid):
        state['n'] += 1
        row = real_get(bid)
        if state['n'] == 1 and row:  # only the pre-atomic read is forced stale-pending
            row = dict(row)
            row['status'] = 'pending_confirm'
        return row
    monkeypatch.setattr(svc.repo, 'get_booking', fake_get)

    cr2 = svc.confirm_booking(token)
    assert cr2.success and cr2.status_code == 200 and cr2.data['status'] == 'confirmed'
    assert cr2.data['fp_id'] == fp_id

    b = real_get(booking_id)
    assert b['status'] == 'confirmed'  # NOT 'conflict'
    assert repo.query_one('SELECT id FROM foi_de_parcurs WHERE id=%s', (fp_id,)) is not None
    free_ids = {s['id'] for s in svc.slots.available_slots(
        p['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))}
    assert slot['id'] not in free_ids


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


def test_confirm_maps_licence_and_consents_onto_fp(open_page):
    """A booking submitted with the legal fields (driving licence + GDPR /
    conditions consents) maps them onto the confirmed fișă and mirrors the
    licence onto the CRM client."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(
        _SLUG, slot['id'], 'Ana', _PHONE, _EMAIL, {}, '1.2.3.4', 'ua', 'x',
        extra_answers={'license': 'AB 123456', 'license_expiry': '2030-05-01',
                       'gdpr_consent': True, 'conditions_accepted': True})
    assert r.success and r.status_code == 201
    # Stored on the booking as extra_answers.
    ea = repo.get_booking(r.data['booking_id'])['extra_answers']
    assert ea['license'] == 'AB 123456'

    cr = svc.confirm_booking(make_booking_token(r.data['booking_id'], 'confirm', current_app.secret_key))
    assert cr.success and cr.status_code == 200

    fp = repo.query_one('SELECT * FROM foi_de_parcurs WHERE id=%s', (cr.data['fp_id'],))
    assert fp['driver_license_number'] == 'AB 123456'
    assert fp['driver_license_expiry'] == '2030-05-01'
    assert fp['gdpr_consent'] is True
    assert fp['general_conditions_accepted'] is True
    assert fp['general_conditions_accepted_at'] is not None

    # The licence is mirrored onto the (newly-created) CRM client.
    crm = repo.query_one('SELECT driver_license_number FROM crm_clients WHERE phone=%s', (_PHONE,))
    assert crm and crm['driver_license_number'] == 'AB 123456'


# ---- multi-car / multi-interval GROUP ----

def test_submit_group_two_slots_shares_group_id_one_email(open_page):
    """A submit with two slot_ids creates two bookings that share one group_id,
    reports both as booked, and sends exactly ONE confirmation email."""
    svc, p, c, sent = open_page
    s1, s2 = _two_nonadjacent_slots(svc, p)
    r = svc.submit_booking(_SLUG, name='Ana', phone_e164=_PHONE, email=_EMAIL,
                           utm={}, ip='1.2.3.4', user_agent='ua', base_url='x',
                           slot_ids=[s1['id'], s2['id']])
    assert r.success and r.status_code == 201
    assert len(r.data['booked']) == 2
    assert r.data['unavailable'] == []
    gid = r.data['group_id']
    rows = repo.get_group(gid)
    assert len(rows) == 2
    assert {row['slot_id'] for row in rows} == {s1['id'], s2['id']}
    assert all(row['group_id'] == gid for row in rows)
    assert all(row['status'] == 'pending_confirm' for row in rows)
    assert len(sent) == 1  # ONE email for the whole group


def test_group_confirm_token_confirms_both(open_page):
    """The group confirm token confirms BOTH bookings -> two PLANNED fișe."""
    svc, p, c, sent = open_page
    s1, s2 = _two_nonadjacent_slots(svc, p)
    r = svc.submit_booking(_SLUG, name='Ana', phone_e164=_PHONE, email=_EMAIL,
                           utm={}, ip='1.2.3.4', user_agent='ua', base_url='x',
                           slot_ids=[s1['id'], s2['id']])
    gid = r.data['group_id']

    cr = svc.confirm_booking(make_group_token(gid, 'confirm', current_app.secret_key))
    assert cr.success and cr.status_code == 200
    assert cr.data['confirmed'] == 2 and cr.data['conflicts'] == 0

    rows = repo.get_group(gid)
    fp_ids = [row['foi_de_parcurs_id'] for row in rows]
    assert all(fp_ids) and len(set(fp_ids)) == 2
    for fid in fp_ids:
        fp = repo.query_one('SELECT status, route_type FROM foi_de_parcurs WHERE id=%s', (fid,))
        assert fp['status'] == 'PLANNED' and fp['route_type'] == 'TD'
    assert all(row['status'] == 'confirmed' for row in rows)


def test_group_submit_skips_already_taken_slot(open_page):
    """A slot already held by another contact is dropped from the group and
    flagged 'unavailable'; the rest of the group still succeeds."""
    svc, p, c, sent = open_page
    s1, s2 = _two_nonadjacent_slots(svc, p)
    # Another contact grabs s1 first (a group of one).
    r0 = svc.submit_booking(_SLUG, name='Bob', phone_e164=_PHONE2, email=_EMAIL2,
                            utm={}, ip='9.9.9.9', user_agent='ua', base_url='x',
                            slot_ids=[s1['id']])
    assert r0.success

    r = svc.submit_booking(_SLUG, name='Ana', phone_e164=_PHONE, email=_EMAIL,
                           utm={}, ip='1.2.3.4', user_agent='ua', base_url='x',
                           slot_ids=[s1['id'], s2['id']])
    assert r.success and r.status_code == 201
    assert [b['slot_id'] for b in r.data['booked']] == [s2['id']]
    assert r.data['unavailable'] == [s1['id']]
    rows = repo.get_group(r.data['group_id'])
    assert len(rows) == 1 and rows[0]['slot_id'] == s2['id']


def test_group_cancel_cancels_all_and_deletes_fise(open_page):
    """The group cancel token cancels every booking in the group and hard-deletes
    each PLANNED fișă, freeing the slots again."""
    svc, p, c, sent = open_page
    s1, s2 = _two_nonadjacent_slots(svc, p)
    r = svc.submit_booking(_SLUG, name='Ana', phone_e164=_PHONE, email=_EMAIL,
                           utm={}, ip='1.2.3.4', user_agent='ua', base_url='x',
                           slot_ids=[s1['id'], s2['id']])
    gid = r.data['group_id']
    cr = svc.confirm_booking(make_group_token(gid, 'confirm', current_app.secret_key))
    fp_ids = [row['foi_de_parcurs_id'] for row in repo.get_group(gid)]
    assert cr.data['confirmed'] == 2 and all(fp_ids)

    xr = svc.cancel_booking(make_group_token(gid, 'cancel', current_app.secret_key))
    assert xr.success and xr.status_code == 200 and xr.data['status'] == 'cancelled'

    assert all(row['status'] == 'cancelled' for row in repo.get_group(gid))
    for fid in fp_ids:
        assert repo.query_one('SELECT id FROM foi_de_parcurs WHERE id=%s', (fid,)) is None
    free_ids = {s['id'] for s in svc.slots.available_slots(
        p['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))}
    assert s1['id'] in free_ids and s2['id'] in free_ids


def test_group_of_one_keeps_single_shape(open_page):
    """A single-slot submit still exposes the legacy booking_id + status fields
    (a group of one), so existing single-slot callers keep working."""
    svc, p, c, sent = open_page
    slot = _first_slot(svc, p)
    r = svc.submit_booking(_SLUG, name='Ana', phone_e164=_PHONE, email=_EMAIL,
                           utm={}, ip='1.2.3.4', user_agent='ua', base_url='x',
                           slot_ids=[slot['id']])
    assert r.success and r.status_code == 201
    assert r.data['status'] == 'pending_confirm'
    assert 'booking_id' in r.data and r.data['group_id']
    assert len(sent) == 1


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
