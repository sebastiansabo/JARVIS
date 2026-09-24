"""Real-DB tests for the Event TD waiting list (mkt_td_waitlist)."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from marketing.services.td_booking_service import TdBookingService  # noqa: E402

repo = TdBookingRepository()
svc = TdBookingService()
_SLUG = 'cfa-waitlist-1'


def _company_id():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        return cur.fetchone()['id']
    finally:
        release_db(conn)


def _clean():
    for pg in repo.query_all("SELECT id FROM mkt_td_booking_pages WHERE slug=%s", (_SLUG,)):
        repo.execute("DELETE FROM mkt_td_waitlist WHERE page_id=%s", (pg['id'],))
        repo.execute("DELETE FROM mkt_td_booking_pages WHERE id=%s", (pg['id'],))


@pytest.fixture
def page(require_real_db):
    _clean()
    p = repo.create_page({'company_id': _company_id(), 'slug': _SLUG, 'status': 'open', 'created_by': 1})
    yield p
    _clean()


def test_create_list_and_status(page):
    e = repo.create_waitlist_entry({
        'page_id': page['id'], 'customer_name': 'Ana', 'customer_phone_e164': '+40721000010',
        'customer_email': 'ana@ex.com', 'preferred_car_vin': 'VIN123', 'note': 'Aș vrea MG ZS',
    })
    assert e['status'] == 'new' and e['handled_at'] is None

    rows = repo.list_waitlist(page['id'])
    assert len(rows) == 1 and rows[0]['customer_name'] == 'Ana' and rows[0]['note'] == 'Aș vrea MG ZS'

    upd = repo.set_waitlist_status(e['id'], 'contacted', handled_by=1)
    assert upd['status'] == 'contacted' and upd['handled_at'] is not None and upd['handled_by'] == 1

    # Back to 'new' clears the handled timestamp.
    back = repo.set_waitlist_status(e['id'], 'new')
    assert back['status'] == 'new' and back['handled_at'] is None


def test_service_submit_requires_gdpr_and_is_idempotent(page):
    # No GDPR consent -> 422, nothing stored.
    r = svc.submit_waitlist(_SLUG, name='Bob', phone='+40721000011', gdpr_consent=False, ip='1.2.3.4')
    assert not r.success and r.status_code == 422
    assert repo.list_waitlist(page['id']) == []

    # Valid submit -> 201, consent + ip persisted.
    r = svc.submit_waitlist(_SLUG, name='Bob', phone='+40721000011', email='bob@ex.com',
                            preferred_car_vin='VINX', note='dupa-amiaza',
                            gdpr_consent=True, ip='1.2.3.4')
    assert r.success and r.status_code == 201
    rows = repo.list_waitlist(page['id'])
    assert len(rows) == 1 and rows[0]['gdpr_consent'] is True and rows[0]['ip'] == '1.2.3.4'
    first_id = r.data['id']

    # Repeat from the same phone while still 'new' -> idempotent (same id, no dup row).
    r2 = svc.submit_waitlist(_SLUG, name='Bob Again', phone='+4072 100 0011', gdpr_consent=True, ip='1.2.3.4')
    assert r2.success and r2.status_code == 200 and r2.data['id'] == first_id
    assert len(repo.list_waitlist(page['id'])) == 1


def test_service_submit_rejects_bad_phone(page):
    r = svc.submit_waitlist(_SLUG, name='X', phone='not-a-phone', gdpr_consent=True, ip='9.9.9.9')
    assert not r.success and r.status_code == 422
