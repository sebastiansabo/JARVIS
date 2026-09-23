"""Real-DB tests for TdBookingRepository (pages/cars/windows CRUD).

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): the `page`
fixture resolves a real seed company id once via a direct SELECT. created_by/
default_advisor_user_id use users id=1, which does exist in the seed DB.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()


@pytest.fixture
def page(require_real_db):
    # companies has no row with id=1 in this dev DB (and no `deleted_at` column —
    # it uses `is_active` instead), so resolve a real, active seed company id here.
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    p = repo.create_page({'company_id': company_id, 'slug': 'test-event-xyz',
                          'title': 'Test Drive Event', 'created_by': 1})
    yield p
    # FK cascades (page_id ON DELETE CASCADE) clean up any cars/windows created in tests.
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_create_and_fetch_page(page):
    assert page['id'] and page['status'] == 'draft'
    assert repo.get_page_by_slug('test-event-xyz')['id'] == page['id']


def test_add_car_and_window(page):
    car = repo.add_car(page['id'], vin='WVWZZZ1', vehicle_id=None,
                       default_advisor_user_id=1, sort_order=0)
    assert car['vin'] == 'WVWZZZ1'
    assert repo.list_cars(page['id'])[0]['id'] == car['id']
    w = repo.add_window(page['id'], '2026-10-01', '10:00', '12:00', slot_minutes=30)
    assert w['id'] and repo.list_windows(page['id'])[0]['id'] == w['id']


def test_set_page_status(page):
    assert repo.set_page_status(page['id'], 'open')['status'] == 'open'


def test_conditions_text_create_and_update(page):
    """conditions_text is whitelisted in _PAGE_COLS: settable at create and via
    update_page, and persisted on the page row."""
    created = repo.create_page({'company_id': page['company_id'], 'slug': 'test-cond-xyz',
                               'created_by': 1, 'conditions_text': 'Clauze inițiale.'})
    try:
        assert created['conditions_text'] == 'Clauze inițiale.'
        updated = repo.update_page(created['id'], {'conditions_text': 'Clauze actualizate.'})
        assert updated['conditions_text'] == 'Clauze actualizate.'
    finally:
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (created['id'],))
