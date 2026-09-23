"""Real-DB tests for TdBookingRepository bookings (create w/ race guard, rate-limit
counts, status mutations, expiry).

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): the `slot`
fixture resolves a real seed company id once via a direct SELECT, mirroring
test_td_booking_repository.py / test_td_slots_repository.py. created_by/
default_advisor_user_id use users id=1, which does exist in the seed DB.

mkt_td_bookings has plain (non-CASCADE) FKs to mkt_td_booking_pages/mkt_td_slots/
mkt_td_booking_cars, so any booking row created in a test must be deleted before the
`slot` fixture's page teardown runs, or that DELETE raises a FK violation.

Imports the REAL psycopg2 (not the process-wide mock installed for the rest of the
suite) so pytest.raises(psycopg2.errors.UniqueViolation) catches a genuine violation
raised by the partial-unique index uq_mkt_td_active_booking_per_slot — this is the
whole point of the race-guard test.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
import psycopg2  # noqa: E402  (real driver, bound by conftest's require_real_db probe)
from datetime import datetime, timezone, timedelta  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()


@pytest.fixture
def slot(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    p = repo.create_page({'company_id': company_id, 'slug': 'bk-test-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='BK000001', default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': 'BK000001',
                             'starts_at': '2026-10-01 10:00+03', 'ends_at': '2026-10-01 10:30+03'}])
    s = repo.list_open_slots(p['id'])[0]
    yield p, c, s
    # mkt_td_bookings has NO ON DELETE CASCADE from page/slot/car -> delete any
    # bookings created by the test before the page (and its slots/cars, which DO
    # cascade) is torn down, or this DELETE hits an FK violation.
    repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (p['id'],))
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def _booking_data(p, c, s, **overrides):
    data = {'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
            'customer_name': 'Ion', 'customer_phone_e164': '+40721000001',
            'customer_email': 'ion@example.com',
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=45)}
    data.update(overrides)
    return data


def test_create_booking_whitelists_and_defaults_status(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))
    assert b['id']
    assert b['status'] == 'pending_confirm'
    assert b['page_id'] == p['id']
    assert b['slot_id'] == s['id']
    assert b['car_id'] == c['id']
    assert b['customer_name'] == 'Ion'


def test_partial_unique_blocks_second_active_booking(slot):
    p, c, s = slot
    b1 = repo.create_booking(_booking_data(p, c, s))
    assert b1['status'] == 'pending_confirm'
    with pytest.raises(psycopg2.errors.UniqueViolation):
        repo.create_booking(_booking_data(p, c, s))   # same slot, still active -> blocked

    # the failed attempt must not have left a stray row behind
    assert len(repo.list_bookings(p['id'])) == 1


def test_cancel_frees_slot(slot):
    p, c, s = slot
    b1 = repo.create_booking(_booking_data(p, c, s))
    cancelled = repo.mark_cancelled(b1['id'])
    assert cancelled['status'] == 'cancelled'
    assert cancelled['cancelled_at'] is not None

    b2 = repo.create_booking(_booking_data(p, c, s))   # now allowed
    assert b2['id'] != b1['id']


def test_get_booking(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))
    fetched = repo.get_booking(b['id'])
    assert fetched['id'] == b['id']
    assert repo.get_booking(-1) is None


def test_list_bookings_filters_by_status(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))
    all_bookings = repo.list_bookings(p['id'])
    assert len(all_bookings) == 1
    assert all_bookings[0]['id'] == b['id']

    pending = repo.list_bookings(p['id'], status='pending_confirm')
    assert len(pending) == 1

    confirmed = repo.list_bookings(p['id'], status='confirmed')
    assert confirmed == []


def test_count_active_by_contact(slot):
    p, c, s = slot
    phone = '+40721009999'
    email = 'contact-count@example.com'
    assert repo.count_active_by_contact(phone, email) == 0

    repo.create_booking(_booking_data(p, c, s, customer_phone_e164=phone, customer_email=email))
    assert repo.count_active_by_contact(phone, email) == 1
    # matches on phone OR email alone too
    assert repo.count_active_by_contact(phone, 'other@example.com') == 1
    assert repo.count_active_by_contact('+40700000000', email) == 1


def test_count_active_by_contact_excludes_cancelled(slot):
    p, c, s = slot
    phone = '+40721008888'
    email = 'cancelled-count@example.com'
    b = repo.create_booking(_booking_data(p, c, s, customer_phone_e164=phone, customer_email=email))
    repo.mark_cancelled(b['id'])
    assert repo.count_active_by_contact(phone, email) == 0


def test_count_recent_by_ip(slot):
    p, c, s = slot
    ip = '203.0.113.42'
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert repo.count_recent_by_ip(ip, since) == 0

    repo.create_booking(_booking_data(p, c, s, ip=ip))
    assert repo.count_recent_by_ip(ip, since) == 1

    future_since = datetime.now(timezone.utc) + timedelta(hours=1)
    assert repo.count_recent_by_ip(ip, future_since) == 0


def test_mark_confirmed(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))
    confirmed = repo.mark_confirmed(b['id'], crm_client_id=42, foi_de_parcurs_id=7,
                                     advisor_user_id=1)
    assert confirmed['status'] == 'confirmed'
    assert confirmed['crm_client_id'] == 42
    assert confirmed['foi_de_parcurs_id'] == 7
    assert confirmed['advisor_user_id'] == 1
    assert confirmed['confirmed_at'] is not None


def test_mark_status(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))
    updated = repo.mark_status(b['id'], 'no_show')
    assert updated['status'] == 'no_show'


def test_extra_answers_and_utm_json_roundtrip(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(
        p, c, s,
        extra_answers={'preferred_time': 'morning'},
        utm={'source': 'facebook', 'campaign': 'td-launch'},
    ))
    fetched = repo.get_booking(b['id'])
    assert fetched['extra_answers'] == {'preferred_time': 'morning'}
    assert fetched['utm'] == {'source': 'facebook', 'campaign': 'td-launch'}


def test_expire_pending(slot):
    p, c, s = slot
    d = _booking_data(p, c, s)
    d['expires_at'] = datetime.now(timezone.utc) - timedelta(minutes=1)
    b = repo.create_booking(d)
    assert repo.expire_pending(datetime.now(timezone.utc)) >= 1
    assert repo.get_booking(b['id'])['status'] == 'expired'


def test_expire_pending_ignores_future_expiry(slot):
    p, c, s = slot
    b = repo.create_booking(_booking_data(p, c, s))  # expires 45 min from now
    # only expire bookings whose expiry is far in the past; this one is untouched
    repo.expire_pending(datetime.now(timezone.utc) - timedelta(hours=1))
    assert repo.get_booking(b['id'])['status'] == 'pending_confirm'
