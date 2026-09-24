"""Task 16: End-to-end happy-path smoke test for the buyback module.

Drives the ENTIRE lifecycle through the real Flask test client (`client` +
`as_role` fixtures from tests/buyback/conftest.py) — no service/repository
called directly — and asserts the terminal state + the CarPark hand-off +
the audit trail:

    create -> initial offer -> accept (-> INSPECTION) -> save inspection
    -> final offer -> accept (-> BOUGHT) -> finalize (-> CarPark vehicle)

Everything is driven as Admin per Ruling R4 (see test_carpark_handoff.py's
module docstring): Admin carries the can_access_settings bypass, so both the
`@v2_permission_required` decorator and `_guard_company` pass cleanly for
every step, including `record.finalize`. The Acquisition/Sales/Service roles
would 403 on `_guard_company` in this harness because their 'all'-scope
boundary falls through to a live `get_actable_company_ids()` query that
always returns empty for the harness's fake uids — a harness artifact, not a
real permission gap (already covered by the dedicated permission tests in
test_routes_offers.py/test_routes_inspection.py/test_carpark_handoff.py).

FK gotcha + cleanup: mirrors test_carpark_handoff.py exactly.
`carpark_vehicle_links.linked_by` is a real `NOT NULL REFERENCES users(id)`
column, so the finalizing uid needs a real throwaway `users` row before the
hand-off's `_backlink()` call. The record is created WITHOUT base64 images
so the hand-off's photo carry-over makes no Spaces calls. Every created row
(carpark vehicle, buyback record, throwaway users row) is deleted in a
`finally` block regardless of pass/fail, so this test never leaves data
behind in the shared localhost/defaultdb.
"""
import secrets

import pytest

from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.usefixtures('require_real_db')

_VIN_ALPHABET = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'  # no I/O/Q


def _vin():
    """A fresh, VIN-shape-valid, (with overwhelming probability) unique VIN
    per call — the shared localhost/defaultdb persists carpark vehicles
    across test runs, so a fixed VIN would collide with a prior run's row on
    VehicleService.create_vehicle's duplicate-VIN guard."""
    return 'WBA' + ''.join(secrets.choice(_VIN_ALPHABET) for _ in range(14))


def _ensure_real_user_row(uid):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            'INSERT INTO users (id, name, email) VALUES (%s, %s, %s) '
            'ON CONFLICT (id) DO NOTHING',
            (uid, f'Buyback Smoke Test {uid}', f'buyback-smoke-{uid}@x.test'),
        )
        conn.commit()
    finally:
        release_db(conn)


def test_full_happy_path_smoke(client, as_role):
    vin = _vin()
    record_id = None
    vehicle_id = None
    finalizer_uid = None

    try:
        # ── CREATE ──────────────────────────────────────────────────────
        as_role('Admin', 1)
        r = client.post('/api/buyback/records', json={
            'vin': vin,
            'brand': 'BMW',
            'model': 'X3',
            'acquisition_type': 'buyback',
            'client_type': 'person',
            'client_asking_price_eur': 10000,
            'seller_email': 's@e.z',
            'seller_name': 'Ion Popescu',
        })
        assert r.status_code == 201, r.get_json()
        record = r.get_json()['record']
        record_id = record['id']
        assert record['status'] == 'PENDING_EVALUATION'

        # ── INITIAL OFFER -> accept -> INSPECTION ──────────────────────
        as_role('Admin', 1)
        r = client.post(
            f'/api/buyback/records/{record_id}/offers',
            json={'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'},
        )
        assert r.status_code == 201, r.get_json()
        initial_offer_id = r.get_json()['offer']['id']

        as_role('Admin', 1)
        r = client.post(
            f'/api/buyback/records/{record_id}/offers/{initial_offer_id}/decision',
            json={'decision': 'accepted'},
        )
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['record']['status'] == 'INSPECTION'

        # ── INSPECTION FIELDS ────────────────────────────────────────────
        as_role('Admin', 1)
        r = client.put(
            f'/api/buyback/records/{record_id}/inspection',
            json={'inspection_rating': 4, 'reconditioning_cost_eur': 300},
        )
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['record']['inspection_rating'] == 4

        # ── FINAL OFFER -> accept -> BOUGHT ─────────────────────────────
        as_role('Admin', 1)
        r = client.post(
            f'/api/buyback/records/{record_id}/offers',
            json={'offer_type': 'final', 'amount_eur': 8500, 'vat_status': 'no_vat'},
        )
        assert r.status_code == 201, r.get_json()
        final_offer_id = r.get_json()['offer']['id']
        final_offer_amount = 8500

        as_role('Admin', 1)
        r = client.post(
            f'/api/buyback/records/{record_id}/offers/{final_offer_id}/decision',
            json={'decision': 'accepted'},
        )
        assert r.status_code == 200, r.get_json()
        bought = r.get_json()['record']
        assert bought['status'] == 'BOUGHT'
        assert bought['carpark_vehicle_id'] is None  # not handed off yet

        # ── FINALIZE -> CarPark hand-off ─────────────────────────────────
        # linked_by needs a real users row (see module docstring's FK gotcha).
        finalizer_uid = as_role('Admin', 1)
        _ensure_real_user_row(finalizer_uid)

        r = client.post(f'/api/buyback/records/{record_id}/finalize', json={})
        assert r.status_code == 200, r.get_json()
        fin_body = r.get_json()
        assert fin_body['success'] is True
        final_record = fin_body['record']
        vehicle_id = final_record.get('carpark_vehicle_id')

        # ── Terminal-state assertions ─────────────────────────────────────
        assert final_record['status'] == 'BOUGHT'
        assert vehicle_id
        assert float(final_record['purchase_price_eur']) == final_offer_amount

        from carpark.repositories.vehicle_repository import VehicleRepository
        vehicle = VehicleRepository().get_by_id(vehicle_id)
        assert vehicle is not None
        assert vehicle['source'] in ('BUY BACK PF', 'BUY BACK PJ')
        assert float(vehicle['purchase_price_net']) == final_offer_amount
        assert vehicle['vin'] == vin

        # ── Audit trail: a status_changed event per transition ───────────
        as_role('Admin', 1)
        detail = client.get(f'/api/buyback/records/{record_id}')
        assert detail.status_code == 200, detail.get_json()
        detail_body = detail.get_json()
        assert detail_body['record']['id'] == record_id
        assert detail_body['record']['status'] == 'BOUGHT'
        assert detail_body['record']['carpark_vehicle_id'] == vehicle_id

        status_changed_events = [
            e for e in detail_body['events'] if e['action'] == 'status_changed'
        ]
        # Every status flip in the flow (PENDING_EVALUATION->INITIAL_OFFER
        # on the initial offer post, INITIAL_OFFER->INSPECTION on accept,
        # INSPECTION->FINAL_OFFER on the final offer post, FINAL_OFFER->
        # BOUGHT on accept) is logged via BuyBackService.transition(), so
        # the trail must have (at least) one status_changed event per hop,
        # each carrying {'from': ..., 'to': ...} in `details`.
        assert len(status_changed_events) >= 4
        statuses_reached = {e['details']['to'] for e in status_changed_events}
        assert {'INITIAL_OFFER', 'INSPECTION', 'FINAL_OFFER', 'BOUGHT'} <= statuses_reached

        # Offers + photos are present in the detail payload too.
        assert len(detail_body['offers']) >= 2
        assert isinstance(detail_body['photos'], list)

    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            if vehicle_id:
                cur.execute('DELETE FROM carpark_vehicles WHERE id = %s', (vehicle_id,))
            if record_id:
                cur.execute('DELETE FROM buyback_records WHERE id = %s', (record_id,))
            if finalizer_uid:
                cur.execute('DELETE FROM users WHERE id = %s', (finalizer_uid,))
            conn.commit()
        finally:
            release_db(conn)
