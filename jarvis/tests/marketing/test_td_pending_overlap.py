"""Real-DB tests for TdBookingRepository.has_pending_overlap — a still-live
`pending_confirm` hold on a VIN whose slot overlaps [frm, to).

This closes the gap the foi_de_parcurs-based checks can't see: a pending hold has
NO foi_de_parcurs row yet, so without this an overlapping slot on the same car
(e.g. the same VIN offered on another page) would look free until the hold is
confirmed or its confirmation window expires. Once this is wired into
TdSlotService.is_car_free, availability + submit stop offering the overlap.

Real localhost DB via require_real_db (skips cleanly without one); real psycopg2.
mkt_td_bookings has plain (non-CASCADE) FKs, so bookings are deleted before the
page (whose slots/cars DO cascade) in teardown.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from datetime import datetime, timezone, timedelta  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()

_VIN = 'CFAPEND001'
_SLUG = 'cfa-pending-1'
_FRM = '2099-11-01 10:00+03'
_TO = '2099-11-01 10:30+03'


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


def _clean():
    for pg in repo.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (_SLUG,)):
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))


@pytest.fixture
def pending(require_real_db):
    _clean()
    company_id = _resolve_company_id()
    p = repo.create_page({'company_id': company_id, 'slug': _SLUG, 'created_by': 1})
    c = repo.add_car(p['id'], vin=_VIN, default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': _VIN,
                             'starts_at': _FRM, 'ends_at': _TO}])
    s = repo.list_open_slots(p['id'])[0]
    b = repo.create_booking({'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
                             'customer_name': 'Ana', 'customer_phone_e164': '+40721000010',
                             'customer_email': 'ana@ex.com', 'group_id': 'grpPEND1',
                             'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)})
    yield p, c, s, b
    _clean()


def test_live_hold_blocks_overlapping_window(pending):
    now = datetime.now(timezone.utc)
    # A window [10:15, 10:45) overlaps the held [10:00, 10:30).
    assert repo.has_pending_overlap(_VIN, now, '2099-11-01 10:15+03', '2099-11-01 10:45+03') is True
    # The exact held window overlaps too.
    assert repo.has_pending_overlap(_VIN, now, _FRM, _TO) is True


def test_live_hold_ignores_nonoverlapping_window(pending):
    now = datetime.now(timezone.utc)
    # [10:30, 11:00) is adjacent but does NOT overlap the half-open [10:00, 10:30).
    assert repo.has_pending_overlap(_VIN, now, '2099-11-01 10:30+03', '2099-11-01 11:00+03') is False


def test_hold_only_matches_same_vin(pending):
    now = datetime.now(timezone.utc)
    assert repo.has_pending_overlap('OTHERVIN9', now, _FRM, _TO) is False


def test_expired_hold_does_not_block(pending):
    _p, _c, _s, b = pending
    repo.execute("UPDATE mkt_td_bookings SET expires_at=%s WHERE id=%s",
                 (datetime.now(timezone.utc) - timedelta(minutes=1), b['id']))
    now = datetime.now(timezone.utc)
    assert repo.has_pending_overlap(_VIN, now, _FRM, _TO) is False


def test_non_pending_hold_does_not_block(pending):
    _p, _c, _s, b = pending
    repo.execute("UPDATE mkt_td_bookings SET status='cancelled' WHERE id=%s", (b['id'],))
    now = datetime.now(timezone.utc)
    assert repo.has_pending_overlap(_VIN, now, _FRM, _TO) is False
