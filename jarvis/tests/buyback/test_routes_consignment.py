"""Route tests for the consignment proposal flow (Propune consignație):
POST /records/<id>/propose-consignment (opens a 'consignment' offer from
PENDING_EVALUATION) and the accept/decline that runs through the existing
POST /records/<id>/offers/<oid>/decision route.

DB-backed, driven end-to-end as Admin — same Ruling R4 rationale and FK/user
gotcha as tests/buyback/test_carpark_handoff.py (see that module's docstring):
Acquisition's 'all'-scope boundary falls through to a live org query that
returns empty for the fake harness uids, so the whole flow is driven as Admin
(can_access_settings bypass), and any request that reaches a real hand-off
gets a real `users` row minted for its uid (carpark_vehicle_links.linked_by is
a NOT NULL FK).
"""
import secrets

import pytest

from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.usefixtures('require_real_db')


_VIN_ALPHABET = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'  # no I/O/Q


def _vin():
    return 'WBA' + ''.join(secrets.choice(_VIN_ALPHABET) for _ in range(14))


def _payload(vin, **overrides):
    data = {
        'vin': vin, 'brand': 'BMW', 'model': '320d',
        'acquisition_type': 'buyback', 'client_type': 'person',
        'client_asking_price_eur': 1000, 'seller_email': 's@e.z',
        'seller_name': 'Ion Popescu', 'seller_cui': None,
    }
    data.update(overrides)
    return data


_AGREEMENT = {
    'commission_type': 'percent', 'commission_value': 10,
    'owner_price': 15000, 'min_sale_price': 14000,
    'contract_number': 'CS-9', 'agreement_date': '2026-10-14', 'expiry_date': '2027-01-01',
}


def _ensure_real_user_row(uid):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            'INSERT INTO users (id, name, email) VALUES (%s, %s, %s) '
            'ON CONFLICT (id) DO NOTHING',
            (uid, f'Consignment Test {uid}', f'consignment-{uid}@x.test'),
        )
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture
def _tracked():
    state = {'record_ids': [], 'vehicle_ids': [], 'uids': []}
    yield state
    conn = get_db()
    try:
        cur = get_cursor(conn)
        if state['vehicle_ids']:
            cur.execute('DELETE FROM carpark_vehicles WHERE id = ANY(%s)', (state['vehicle_ids'],))
        if state['record_ids']:
            cur.execute('DELETE FROM buyback_records WHERE id = ANY(%s)', (state['record_ids'],))
        if state['uids']:
            cur.execute('DELETE FROM users WHERE id = ANY(%s)', (state['uids'],))
        conn.commit()
    finally:
        release_db(conn)


def _create_record(client, as_role, tracked, vin, company_id=1):
    as_role('Admin', company_id)
    r = client.post('/api/buyback/records', json=_payload(vin))
    assert r.status_code == 201, r.get_json()
    rid = r.get_json()['record']['id']
    tracked['record_ids'].append(rid)
    return rid


# ── PROPOSE ────────────────────────────────────────────────────────────────

def test_propose_consignment_opens_offer_and_advances(client, as_role, _tracked):
    rid = _create_record(client, as_role, _tracked, _vin())

    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/propose-consignment', json=_AGREEMENT)
    assert r.status_code == 201, r.get_json()
    offer = r.get_json()['offer']
    assert offer['offer_type'] == 'consignment'
    assert offer['client_decision'] == 'pending'
    assert offer['consignment_terms']['commission_type'] == 'percent'
    assert float(offer['consignment_terms']['owner_price']) == 15000

    detail = client.get(f'/api/buyback/records/{rid}').get_json()
    assert detail['record']['status'] == 'CONSIGNMENT_OFFER'


def test_propose_consignment_bad_agreement_is_400(client, as_role, _tracked):
    rid = _create_record(client, as_role, _tracked, _vin())
    as_role('Admin', 1)
    r = client.post(
        f'/api/buyback/records/{rid}/propose-consignment',
        json={'commission_type': 'maybe', 'commission_value': 1},
    )
    assert r.status_code == 400, r.get_json()
    detail = client.get(f'/api/buyback/records/{rid}').get_json()
    assert detail['record']['status'] == 'PENDING_EVALUATION'  # unchanged


def test_propose_consignment_wrong_status_is_409(client, as_role, _tracked):
    """A consignment proposal is only valid from PENDING_EVALUATION; after an
    initial buy offer the record is INITIAL_OFFER → 409."""
    rid = _create_record(client, as_role, _tracked, _vin())
    as_role('Admin', 1)
    client.post(f'/api/buyback/records/{rid}/offers',
                json={'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'})
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/propose-consignment', json=_AGREEMENT)
    assert r.status_code == 409, r.get_json()


def test_propose_consignment_missing_record_is_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/propose-consignment', json=_AGREEMENT)
    assert r.status_code == 404


# ── DECLINE → LOST ───────────────────────────────────────────────────────────

def test_consignment_decline_moves_record_to_lost(client, as_role, _tracked):
    rid = _create_record(client, as_role, _tracked, _vin())
    as_role('Admin', 1)
    oid = client.post(f'/api/buyback/records/{rid}/propose-consignment', json=_AGREEMENT).get_json()['offer']['id']

    as_role('Admin', 1)
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision',
                    json={'decision': 'declined', 'decline_reason': 'nu vrea'})
    assert d.status_code == 200, d.get_json()
    assert d.get_json()['record']['status'] == 'LOST'


# ── ACCEPT → CONSIGNAT + real CarPark hand-off ───────────────────────────────

def test_consignment_accept_creates_consignment_vehicle(client, as_role, monkeypatch, _tracked):
    """Accepting the proposal hands the car off to CarPark on consignment:
    is_consignment vehicle (source CUSTODIE, no purchase price), a
    carpark_vehicle_consignment row carrying the proposed terms, the record
    linked + moved to CONSIGNAT. Spaces is mocked (no creds in tests)."""
    import buyback.services.carpark_handoff as handoff_mod
    monkeypatch.setattr(handoff_mod.spaces_service, 'fetch', lambda key: (b'x', 'image/jpeg'))
    monkeypatch.setattr(handoff_mod.spaces_service, 'upload', lambda data, key, ct: key)

    rid = _create_record(client, as_role, _tracked, _vin())
    uid = as_role('Admin', 1)
    _tracked['uids'].append(uid)
    _ensure_real_user_row(uid)
    oid = client.post(f'/api/buyback/records/{rid}/propose-consignment', json=_AGREEMENT).get_json()['offer']['id']

    uid2 = as_role('Admin', 1)
    _tracked['uids'].append(uid2)
    _ensure_real_user_row(uid2)
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert d.status_code == 200, d.get_json()
    rec = d.get_json()['record']
    veh_id = rec.get('carpark_vehicle_id')
    if veh_id:
        _tracked['vehicle_ids'].append(veh_id)

    assert rec['status'] == 'CONSIGNAT'
    assert veh_id

    from carpark.repositories.vehicle_repository import VehicleRepository
    veh = VehicleRepository().get_by_id(veh_id)
    assert veh['is_consignment'] is True
    assert veh['source'] == 'CUSTODIE'
    assert veh['purchase_price_net'] is None

    from carpark.repositories.consignment_repository import ConsignmentRepository
    cons = ConsignmentRepository().get_by_vehicle(veh_id)
    assert cons is not None
    assert cons['commission_type'] == 'percent'
    assert float(cons['owner_price']) == 15000

    # Detail GET embeds the consignment agreement for a CONSIGNAT record.
    detail = client.get(f'/api/buyback/records/{rid}').get_json()
    assert detail['record']['status'] == 'CONSIGNAT'
    assert detail['consignment'] is not None
    assert float(detail['consignment']['owner_price']) == 15000
