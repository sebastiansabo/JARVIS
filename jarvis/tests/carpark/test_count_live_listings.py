"""DB-backed behavior test for VehicleRepository.count_live_listings — the live
channel count that drives the auto LISTED<->READY_FOR_SALE flip. Its predicates
MUST stay identical to the catalog's autovit_published/shopify_published
columns, so this seeds real listing rows and asserts the count tracks them,
including the status exclusions (Autovit removed_* / Shopify non-published).

Seeds a throwaway vehicle + reuses an existing autovit connector and publishing
platform (skips if the local DB has neither). Tears everything down.
"""
import pytest

from carpark.repositories.vehicle_repository import VehicleRepository

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.skipif(
    not REAL_DB_AVAILABLE, reason='Real Postgres not available — skipping count_live_listings test')

_VIN = 'TSTCNTVEH00000001'  # 17 chars, no I/O/Q


@pytest.fixture
def seed():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id FROM connectors WHERE connector_type='autovit' LIMIT 1")
        account_row = cur.fetchone()
        cur.execute("SELECT id FROM carpark_publishing_platforms LIMIT 1")
        platform_row = cur.fetchone()
        if not account_row or not platform_row:
            pytest.skip('no autovit connector / publishing platform seeded locally')
        account_id = account_row['id']
        platform_id = platform_row['id']

        cur.execute('DELETE FROM carpark_vehicles WHERE vin = %s', (_VIN,))
        cur.execute(
            'INSERT INTO carpark_vehicles (vin, brand, model, status) '
            'VALUES (%s, %s, %s, %s) RETURNING id',
            (_VIN, 'TestBrand', 'TestModel', 'READY_FOR_SALE'))
        vehicle_id = cur.fetchone()['id']
        conn.commit()
    finally:
        release_db(conn)

    try:
        yield {'vehicle_id': vehicle_id, 'account_id': account_id, 'platform_id': platform_id}
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('DELETE FROM carpark_autovit_listings WHERE vehicle_id = %s', (vehicle_id,))
            cur.execute('DELETE FROM carpark_vehicle_listings WHERE vehicle_id = %s', (vehicle_id,))
            cur.execute('DELETE FROM carpark_vehicles WHERE id = %s', (vehicle_id,))
            conn.commit()
        finally:
            release_db(conn)


def _exec(sql, params):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(sql, params)
        conn.commit()
    finally:
        release_db(conn)


def test_count_is_zero_without_listings(seed):
    assert VehicleRepository().count_live_listings(seed['vehicle_id']) == 0


def test_count_counts_live_autovit_then_shopify(seed):
    vid = seed['vehicle_id']
    repo = VehicleRepository()

    _exec('INSERT INTO carpark_autovit_listings (vehicle_id, account_id, external_advert_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['account_id'], 'AV1', 'active'))
    assert repo.count_live_listings(vid) == 1

    _exec('INSERT INTO carpark_vehicle_listings (vehicle_id, platform_id, external_listing_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['platform_id'], 'SH1', 'published'))
    assert repo.count_live_listings(vid) == 2


def test_removed_autovit_and_unpublished_shopify_do_not_count(seed):
    vid = seed['vehicle_id']
    repo = VehicleRepository()
    _exec('INSERT INTO carpark_autovit_listings (vehicle_id, account_id, external_advert_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['account_id'], 'AV1', 'removed_by_user'))
    _exec('INSERT INTO carpark_vehicle_listings (vehicle_id, platform_id, external_listing_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['platform_id'], 'SH1', 'draft'))
    assert repo.count_live_listings(vid) == 0


def test_deactivated_inactive_autovit_does_not_count(seed):
    """An Autovit ad deactivated via "Dezactivează" (status 'inactive', advert id
    retained) is no longer live → must not count, so the car reverts out of
    LISTED. Mirrors the Publicat-icon rule, which also hides for inactive ads."""
    vid = seed['vehicle_id']
    _exec('INSERT INTO carpark_autovit_listings (vehicle_id, account_id, external_advert_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['account_id'], 'AV1', 'inactive'))
    assert VehicleRepository().count_live_listings(vid) == 0


def test_autovit_without_external_advert_id_does_not_count(seed):
    """A listing row with no external_advert_id isn't live on the marketplace —
    matches the catalog's `external_advert_id IS NOT NULL` guard."""
    vid = seed['vehicle_id']
    _exec('INSERT INTO carpark_autovit_listings (vehicle_id, account_id, external_advert_id, status) '
          'VALUES (%s, %s, %s, %s)', (vid, seed['account_id'], None, 'active'))
    assert VehicleRepository().count_live_listings(vid) == 0
