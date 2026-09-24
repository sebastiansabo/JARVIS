"""Route tests for the buyback CarPark hand-off (Task 14):
POST /records/<id>/finalize and POST /records/<id>/handoff/retry, plus the
underlying buyback.services.carpark_handoff.handoff_to_carpark service.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py — NOT a `client_as` helper (see
test_routes_records.py's module docstring for why).

Per Ruling R4 (also used throughout test_routes_offers.py/
test_routes_inspection.py): Acquisition holds `record.finalize` at 'all'
scope in the real permission seed (migrations/domains/schema_roles.py::
_seed_buyback_permissions_v2), but its 'all'-scope boundary falls through to
core.organization.manager_utils.get_actable_company_ids() — a live query
against the real `users`/sincron tables that always returns empty for the
as_role() harness's fake uids, so _guard_company would 403 Acquisition for
the WRONG reason (no org mapping, not a real permission gap). The whole
happy-path flow (create -> initial offer -> accept -> inspection -> final
offer -> accept -> finalize) is therefore driven end-to-end as Admin, which
carries the can_access_settings bypass (both the permission decorator and
_guard_company pass cleanly). The cross-company IDOR boundary is exercised
the same way test_routes_offers.py does: authenticate as Admin (clears the
finalize permission decorator) and monkeypatch
_shared._permitted_company_ids directly.

FK GOTCHA this suite works around: carpark_vehicle_links.linked_by is a real
`NOT NULL REFERENCES users(id)` column (unlike buyback_records'/carpark_
vehicles' own created_by/finalized_by columns, which are bare integers with
no FK) — the hand-off's _backlink() call passes current_user.id as
linked_by. The as_role() harness registers a uid in the Flask-Login session
and a fake in-memory user dict, but never inserts a real `users` row for it.
Without a real row, _backlink()'s INSERT hits a ForeignKeyViolation, which
its own best-effort try/except swallows silently — the vehicle would still
be created, but the carpark_vehicle_links row this suite asserts on never
would be. `_ensure_real_user_row()` below inserts a throwaway real `users`
row (id far outside the harness's 980001+ uid range colliding with any real
data — current real max user id is in the low hundreds) for the SPECIFIC
uid that ends up calling finalize/retry, and the `_tracked` fixture deletes
it again in teardown.

CLEANUP: every test that reaches a real hand-off creates a REAL carpark
vehicle (+ status history + photos + link, all ON DELETE CASCADE off
carpark_vehicles) in the shared localhost/defaultdb — the `_tracked` fixture
deletes every record_id/vehicle_id/uid a test registers, in its teardown,
regardless of pass/fail.
"""
import secrets

import pytest

from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.usefixtures('require_real_db')


# ── VIN / payload helpers ────────────────────────────────────────────────

_VIN_ALPHABET = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'  # no I/O/Q


def _vin():
    """A fresh, VIN-shape-valid, (with overwhelming probability) unique VIN
    per call — the shared localhost/defaultdb persists carpark vehicles
    across test runs, so a fixed VIN would collide with a prior run's row on
    VehicleService.create_vehicle's duplicate-VIN guard."""
    return 'WBA' + ''.join(secrets.choice(_VIN_ALPHABET) for _ in range(14))


def _payload(vin, **overrides):
    data = {
        'vin': vin,
        'brand': 'BMW',
        'model': '320d',
        'acquisition_type': 'buyback',
        'client_type': 'person',
        'client_asking_price_eur': 1000,
        'seller_email': 's@e.z',
        'seller_name': 'Ion Popescu',
        'seller_cui': None,
    }
    data.update(overrides)
    return data


# ── DB helpers (cleanup + the FK workaround) ─────────────────────────────

def _ensure_real_user_row(uid):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            'INSERT INTO users (id, name, email) VALUES (%s, %s, %s) '
            'ON CONFLICT (id) DO NOTHING',
            (uid, f'Buyback Handoff Test {uid}', f'buyback-handoff-{uid}@x.test'),
        )
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture
def _tracked():
    """Registry tests append record_ids/vehicle_ids/uids to as they go;
    torn down here regardless of test outcome so this DB-backed suite never
    leaves buyback records, carpark vehicles, or throwaway users rows behind
    in the shared localhost/defaultdb."""
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


# ── Flow builder ──────────────────────────────────────────────────────────

def _to_bought(client, as_role, tracked, vin, company_id=1):
    """Drive a fresh record all the way to BOUGHT (accepted FINAL_OFFER, per
    Task 10's decision route), all as Admin per Ruling R4 — see module
    docstring. Every as_role() call mints a fresh uid, so every step's
    actor is tracked for cleanup too. Returns record_id."""
    as_role('Admin', company_id)
    r = client.post('/api/buyback/records', json=_payload(vin))
    assert r.status_code == 201, r.get_json()
    rid = r.get_json()['record']['id']
    tracked['record_ids'].append(rid)

    as_role('Admin', company_id)
    oid = client.post(
        f'/api/buyback/records/{rid}/offers',
        json={'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'},
    ).get_json()['offer']['id']

    as_role('Admin', company_id)
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert d.status_code == 200, d.get_json()
    assert d.get_json()['record']['status'] == 'INSPECTION'

    as_role('Admin', company_id)
    ins = client.put(
        f'/api/buyback/records/{rid}/inspection',
        json={'inspection_rating': 4, 'reconditioning_cost_eur': 300},
    )
    assert ins.status_code == 200, ins.get_json()

    as_role('Admin', company_id)
    fid = client.post(
        f'/api/buyback/records/{rid}/offers',
        json={'offer_type': 'final', 'amount_eur': 8500, 'vat_status': 'no_vat'},
    ).get_json()['offer']['id']

    as_role('Admin', company_id)
    fd = client.post(f'/api/buyback/records/{rid}/offers/{fid}/decision', json={'decision': 'accepted'})
    assert fd.status_code == 200, fd.get_json()
    assert fd.get_json()['record']['status'] == 'BOUGHT'
    assert fd.get_json()['record']['carpark_vehicle_id'] is None

    return rid


def _login_finalizer(as_role, tracked, company_id=1):
    """Log in as a fresh Admin AND give that uid a real `users` row (see
    module docstring's FK gotcha) — use this right before any request that
    may reach a successful hand-off (finalize/retry)."""
    uid = as_role('Admin', company_id)
    tracked['uids'].append(uid)
    _ensure_real_user_row(uid)
    return uid


# ── FINALIZE — happy path ────────────────────────────────────────────────

def test_finalize_creates_carpark_vehicle(client, as_role, _tracked):
    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)

    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['success'] is True
    rec = body['record']
    assert rec['status'] == 'BOUGHT'
    assert rec['carpark_vehicle_id']
    assert float(rec['purchase_price_eur']) == 8500
    assert 'handoff_error' not in body

    veh_id = rec['carpark_vehicle_id']
    _tracked['vehicle_ids'].append(veh_id)

    from carpark.repositories.vehicle_repository import VehicleRepository
    veh = VehicleRepository().get_by_id(veh_id)
    assert veh is not None
    assert veh['source'] in ('BUY BACK PF', 'BUY BACK PJ')
    assert float(veh['purchase_price_net']) == 8500

    from carpark.repositories.link_repository import VehicleLinkRepository
    links = VehicleLinkRepository().get_by_vehicle(veh_id, entity_type='buyback')
    assert len(links) == 1
    assert links[0]['linked_entity_id'] == rid


def test_finalize_company_buyer_gets_pj_source(client, as_role, _tracked):
    """client_type='company' selects the PJ source string."""
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(_vin(), client_type='company'))
    assert r.status_code == 201, r.get_json()
    rid = r.get_json()['record']['id']
    _tracked['record_ids'].append(rid)

    as_role('Admin', 1)
    oid = client.post(
        f'/api/buyback/records/{rid}/offers',
        json={'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'},
    ).get_json()['offer']['id']
    as_role('Admin', 1)
    client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    as_role('Admin', 1)
    client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 4})
    as_role('Admin', 1)
    fid = client.post(
        f'/api/buyback/records/{rid}/offers',
        json={'offer_type': 'final', 'amount_eur': 7000, 'vat_status': 'no_vat'},
    ).get_json()['offer']['id']
    as_role('Admin', 1)
    client.post(f'/api/buyback/records/{rid}/offers/{fid}/decision', json={'decision': 'accepted'})

    _login_finalizer(as_role, _tracked)
    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 200, r.get_json()
    veh_id = r.get_json()['record']['carpark_vehicle_id']
    assert veh_id
    _tracked['vehicle_ids'].append(veh_id)

    from carpark.repositories.vehicle_repository import VehicleRepository
    veh = VehicleRepository().get_by_id(veh_id)
    assert veh['source'] == 'BUY BACK PJ'


# ── FINALIZE — dup VIN / retry ───────────────────────────────────────────

def test_finalize_dup_vin_keeps_bought_null_and_retryable(client, as_role, monkeypatch, _tracked):
    from carpark.services.vehicle_service import VehicleService

    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)

    with monkeypatch.context() as m:
        m.setattr(
            VehicleService, 'create_vehicle',
            lambda self, data, created_by: (_ for _ in ()).throw(ValueError('duplicate VIN')),
        )
        r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body['success'] is True
        assert body['record']['status'] == 'BOUGHT'
        assert body['record']['carpark_vehicle_id'] is None
        assert body.get('handoff_error')
        # the purchase price was still stamped even though the hand-off failed
        assert float(body['record']['purchase_price_eur']) == 8500

    detail = client.get(f'/api/buyback/records/{rid}').get_json()['record']
    assert detail['status'] == 'BOUGHT'
    assert detail['carpark_vehicle_id'] is None


def test_retry_after_dup_vin_failure_succeeds(client, as_role, monkeypatch, _tracked):
    from carpark.services.vehicle_service import VehicleService

    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)

    with monkeypatch.context() as m:
        m.setattr(
            VehicleService, 'create_vehicle',
            lambda self, data, created_by: (_ for _ in ()).throw(ValueError('duplicate VIN')),
        )
        first = client.post(f'/api/buyback/records/{rid}/finalize', json={})
        assert first.status_code == 200
        assert first.get_json()['record']['carpark_vehicle_id'] is None

    # VehicleService.create_vehicle is back to normal here (monkeypatch context exited)
    _login_finalizer(as_role, _tracked)
    retry = client.post(f'/api/buyback/records/{rid}/handoff/retry', json={})
    assert retry.status_code == 200, retry.get_json()
    rec = retry.get_json()['record']
    assert rec['status'] == 'BOUGHT'
    assert rec['carpark_vehicle_id']
    _tracked['vehicle_ids'].append(rec['carpark_vehicle_id'])


def test_retry_wrong_status_is_409(client, as_role, _tracked):
    """A record that never reached BOUGHT (still FINAL_OFFER) can't be
    retried — retry only operates on the post-finalize BOUGHT+null state."""
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(_vin()))
    rid = r.get_json()['record']['id']
    _tracked['record_ids'].append(rid)

    as_role('Admin', 1)
    r2 = client.post(f'/api/buyback/records/{rid}/handoff/retry', json={})
    assert r2.status_code == 409, r2.get_json()


# ── FINALIZE — already handed off ────────────────────────────────────────

def test_finalize_already_handed_off_is_409(client, as_role, _tracked):
    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)
    first = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert first.status_code == 200, first.get_json()
    veh_id = first.get_json()['record']['carpark_vehicle_id']
    assert veh_id
    _tracked['vehicle_ids'].append(veh_id)

    as_role('Admin', 1)
    second = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert second.status_code == 409, second.get_json()


def test_retry_already_handed_off_is_409(client, as_role, _tracked):
    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)
    first = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert first.status_code == 200, first.get_json()
    veh_id = first.get_json()['record']['carpark_vehicle_id']
    assert veh_id
    _tracked['vehicle_ids'].append(veh_id)

    as_role('Admin', 1)
    retry = client.post(f'/api/buyback/records/{rid}/handoff/retry', json={})
    assert retry.status_code == 409, retry.get_json()


# ── FINALIZE — permission / IDOR ─────────────────────────────────────────

def test_finalize_requires_finalize_permission(client, as_role, _tracked):
    """Sales holds record.view/create/edit but NOT record.finalize —
    module-level 403 from the decorator, before the route body even runs."""
    rid = _to_bought(client, as_role, _tracked, _vin())
    as_role('Sales', 1)
    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 403


def test_finalize_cross_company_forbidden(client, as_role, monkeypatch, _tracked):
    """Mirrors test_routes_offers.py's test_post_offer_cross_company_forbidden:
    isolates the _guard_company boundary itself (rather than depending on a
    real org/sincron mapping for a fake harness user) by authenticating as
    Admin (clears the record.finalize decorator) and monkeypatching the
    permitted-company set to exclude the record's company."""
    import buyback.routes._shared as shared

    rid = _to_bought(client, as_role, _tracked, _vin(), company_id=1)

    as_role('Admin', 1)
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {2})
    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 403


def test_finalize_missing_record_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/finalize', json={})
    assert r.status_code == 404


# ── Photo carry-over ─────────────────────────────────────────────────────

def test_finalize_carries_photos_over(client, as_role, monkeypatch, _tracked):
    """Spaces is disabled in the test environment (no DO_SPACES_* creds) —
    monkeypatch carpark_handoff.spaces_service.fetch/upload to a no-op,
    mirroring tests/buyback/test_routes_inspection.py's Spaces-mocking
    pattern. A buyback photo row is added directly (not via the base64
    create-time upload path) so this test is isolated to the hand-off's own
    _carry_photos step."""
    import buyback.services.carpark_handoff as handoff_mod
    from buyback.routes import _shared as shared

    fake_bytes = b'fake-jpeg-bytes'
    uploaded_keys = []

    monkeypatch.setattr(handoff_mod.spaces_service, 'fetch', lambda key: (fake_bytes, 'image/jpeg'))

    def _fake_upload(data, key, content_type):
        uploaded_keys.append(key)
        return key

    monkeypatch.setattr(handoff_mod.spaces_service, 'upload', _fake_upload)

    rid = _to_bought(client, as_role, _tracked, _vin())
    shared.photos_repo.create(rid, url='private/buyback/x.jpg')

    _login_finalizer(as_role, _tracked)
    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 200, r.get_json()
    veh_id = r.get_json()['record']['carpark_vehicle_id']
    assert veh_id
    _tracked['vehicle_ids'].append(veh_id)

    assert len(uploaded_keys) == 1
    assert uploaded_keys[0].startswith(f'private/carpark/{veh_id}/')

    from carpark.repositories.photo_repository import PhotoRepository as CarparkPhotoRepository
    photos = CarparkPhotoRepository().get_by_vehicle(veh_id)
    assert len(photos) == 1
    assert photos[0]['is_primary'] is True
    assert photos[0]['url'] == uploaded_keys[0]


def test_finalize_with_no_photos_makes_no_spaces_calls(client, as_role, monkeypatch, _tracked):
    """Counterpart to the photo carry-over test: a record with an empty
    gallery must not touch Spaces at all — proves _carry_photos short-circuits
    on an empty list rather than e.g. calling fetch with a falsy key."""
    import buyback.services.carpark_handoff as handoff_mod

    calls = []
    monkeypatch.setattr(handoff_mod.spaces_service, 'fetch', lambda key: calls.append(('fetch', key)))
    monkeypatch.setattr(handoff_mod.spaces_service, 'upload',
                         lambda data, key, ct: calls.append(('upload', key)))

    rid = _to_bought(client, as_role, _tracked, _vin())
    _login_finalizer(as_role, _tracked)
    r = client.post(f'/api/buyback/records/{rid}/finalize', json={})
    assert r.status_code == 200, r.get_json()
    veh_id = r.get_json()['record']['carpark_vehicle_id']
    assert veh_id
    _tracked['vehicle_ids'].append(veh_id)

    assert calls == []
