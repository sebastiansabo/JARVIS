"""Route tests for the buyback record HTTP endpoints (Task 9): list/detail/
create/update/cancel/reopen/delete under /api/buyback/records, gated by
@v2_permission_required('buyback', 'record', <action>) + cross-company IDOR
guards.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py (Task 0) — NOT a `client_as`
helper. Per Ruling R4: happy-path tests authenticate as as_role('Admin', 1)
(admin bypass -> g.permission_scope == 'all'); the Sales role only has 'own'
scope (view/create/edit, no delete) per
migrations/domains/schema_roles.py::_seed_buyback_permissions_v2, so the
cross-company IDOR test uses Sales for both the owner and the intruder.

Requests never send an explicit `company_id` for non-admin (Sales) actors:
_shared._acting_company_id() (copied verbatim from carpark/routes/vehicles.py)
resolves a request-provided company_id against
core.organization.manager_utils.get_actable_company_ids(), which queries the
real `users`/sincron tables — the as_role() fixture's fake users have no such
DB rows, so that lookup would incorrectly 403 a same-company request. The
routes avoid this entirely for 'own'-scope callers by forcing
company_id = current_user.company_id server-side and ignoring any
request-supplied company_id (see records.py list/create), matching the
scope-gating already specified for GET /records in the brief.
"""
import base64
import os

import pytest

pytestmark = pytest.mark.usefixtures('require_real_db')


def _vin():
    # Not checksum-valid (the VIN_RE gate doesn't check-digit, just shape:
    # 17 chars, no I/O/Q), unique per call so parallel/rerun tests never collide.
    import secrets
    alphabet = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'
    return 'WBA' + ''.join(secrets.choice(alphabet) for _ in range(14))


def _payload(**overrides):
    data = {
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'acquisition_type': 'buyback',
        'client_asking_price_eur': 1000,
        'seller_email': 's@e.z',
    }
    data.update(overrides)
    return data


# ── CREATE — VIN validation ─────────────────────────────────────────────

def test_create_requires_valid_vin(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(vin='BADVIN'))
    assert r.status_code == 400
    assert 'VIN' in r.get_json().get('error', '')


def test_create_missing_vin_is_400(client, as_role):
    as_role('Admin', 1)
    data = _payload()
    data.pop('vin')
    r = client.post('/api/buyback/records', json=data)
    assert r.status_code == 400


# ── CREATE + LIST scoped ────────────────────────────────────────────────

def test_create_and_list_scoped(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body['success'] is True
    rec = body['record']
    assert rec['status'] == 'PENDING_EVALUATION'
    assert rec['company_id'] == 1
    assert rec['record_code'].startswith('BB-')

    lst = client.get('/api/buyback/records?company_id=1').get_json()
    assert lst['total'] >= 1
    assert any(r2['id'] == rec['id'] for r2 in lst['records'])


def test_create_response_includes_vin_in_carpark_flag(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload())
    body = r.get_json()
    # Absent VIN in carpark_vehicles for a fresh random VIN -> flag omitted/false
    assert body.get('vin_in_carpark') in (None, False)


# ── CREATE — acquisition-team notification (Task 13 fix round 1) ─────────

def test_create_invokes_notify_acquisition_once(client, as_role, monkeypatch):
    # The CREATE route must fire the acquisition heads-up exactly once, on the
    # just-created record, via the service singleton's notifier — spy on the
    # bound method (restored automatically by monkeypatch after the test).
    from buyback.routes import _shared
    calls = []
    monkeypatch.setattr(
        _shared.service.notifier, 'notify_acquisition',
        lambda record: calls.append(record['id']),
    )
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()
    rid = r.get_json()['record']['id']
    assert calls == [rid]  # called exactly once, with the created record


def test_create_survives_raising_notify_acquisition(client, as_role, monkeypatch):
    # The notification must never turn a successful create into a 500. The route
    # has NO try/except of its own (per the fix-round-1 instruction) — it relies
    # on Notifier.notify_acquisition swallowing its own send_email failures. So
    # we drive the realistic failure mode: a resolvable recipient (env var) +
    # a send_email that raises. The real Notifier must swallow it and the create
    # must still return 201.
    from buyback.services import email as email_module
    monkeypatch.setenv('BUYBACK_ACQUISITION_EMAIL', 'acq@example.com')

    def _raise(**kwargs):
        raise RuntimeError('SMTP is on fire')

    monkeypatch.setattr(email_module, 'send_email', _raise)
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['success'] is True


def test_list_own_scope_ignores_foreign_company_param(client, as_role):
    """Sales has 'own' scope: a Sales user in company 1 must only ever see
    company-1 records, even if they try to pass ?company_id=2."""
    as_role('Sales', 1)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()

    lst = client.get('/api/buyback/records?company_id=2').get_json()
    assert all(rec['company_id'] == 1 for rec in lst['records'])


# ── DETAIL ───────────────────────────────────────────────────────────────

def test_get_detail_includes_offers_photos_events(client, as_role):
    as_role('Admin', 1)
    created = client.post('/api/buyback/records', json=_payload()).get_json()['record']
    r = client.get(f"/api/buyback/records/{created['id']}")
    assert r.status_code == 200
    body = r.get_json()
    assert body['record']['id'] == created['id']
    assert isinstance(body['offers'], list)
    assert isinstance(body['photos'], list)
    assert isinstance(body['events'], list)
    # a 'created' event was logged by the create route
    assert any(e['action'] == 'created' for e in body['events'])


def test_get_detail_missing_404(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/records/999999999')
    assert r.status_code == 404


def test_get_detail_cross_company_forbidden_for_own_scope(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    as_role('Sales', 2)
    r = client.get(f'/api/buyback/records/{rid}')
    assert r.status_code == 403


# ── IDOR — cross-company mutation ───────────────────────────────────────

def test_mutation_cross_company_idor_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']

    as_role('Sales', 2)
    r = client.put(f'/api/buyback/records/{rid}', json={'other_details': 'hacked'})
    assert r.status_code == 403


# ── UPDATE ───────────────────────────────────────────────────────────────

def test_update_whitelisted_field(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'mileage_km': 55555})
    assert r.status_code == 200
    assert r.get_json()['record']['mileage_km'] == 55555


def test_update_rejects_when_not_pending_evaluation(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    cancel = client.post(f'/api/buyback/records/{rid}/cancel', json={'reason': 'test'})
    assert cancel.status_code == 200, cancel.get_json()

    r = client.put(f'/api/buyback/records/{rid}', json={'mileage_km': 1})
    assert r.status_code == 409


def test_update_company_id_in_body_is_ignored(client, as_role):
    """company_id must never be settable via the generic update whitelist —
    RecordRepository._UPDATABLE_COLUMNS already excludes it, this asserts
    the route doesn't work around that."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'company_id': 999, 'mileage_km': 42})
    assert r.status_code == 200
    assert r.get_json()['record']['company_id'] == 1


def test_update_rejects_workflow_only_fields(client, as_role):
    """PUT must not let a plain record.edit caller (even Admin) forge
    workflow/finance fields that only the dedicated offer/inspection/
    purchase stage services (later tasks) may ever set —
    RecordRepository._UPDATABLE_COLUMNS is a SQL-identifier safety
    whitelist, not an authorization boundary, so the route must apply its
    own narrower intake-fields whitelist on top of it."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={
        'purchase_price_eur': 1, 'carpark_vehicle_id': 999,
        'finalized_by': 1, 'bought_at': '2020-01-01T00:00:00Z',
        'closed_at': '2020-01-01T00:00:00Z', 'inspected_by': 1,
        'lost_reason': 'forged',
        'mileage_km': 42,
    })
    assert r.status_code == 200
    rec = r.get_json()['record']
    assert rec['mileage_km'] == 42
    assert rec['purchase_price_eur'] is None
    assert rec['carpark_vehicle_id'] is None
    assert rec['finalized_by'] is None
    assert rec['bought_at'] is None
    assert rec['closed_at'] is None
    assert rec['inspected_by'] is None
    assert rec['lost_reason'] is None


# ── CANCEL / REOPEN ──────────────────────────────────────────────────────

def test_cancel_transitions_status(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.post(f'/api/buyback/records/{rid}/cancel', json={'reason': 'no longer interested'})
    assert r.status_code == 200
    assert r.get_json()['record']['status'] == 'CANCELLED'


def test_cancel_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    as_role('Sales', 2)
    r = client.post(f'/api/buyback/records/{rid}/cancel', json={'reason': 'x'})
    assert r.status_code == 403


def test_reopen_requires_admin_or_manager(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    client.post(f'/api/buyback/records/{rid}/cancel', json={'reason': 'x'})
    # cancelled has no valid transition back to PENDING_EVALUATION anyway,
    # but a non-admin/manager must be blocked before that's even checked.
    r = client.post(f'/api/buyback/records/{rid}/reopen')
    assert r.status_code == 403


def test_reopen_from_lost_by_admin(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    # Drive the record to LOST via the service directly (no offer/decision
    # routes exist yet — those land in a later task) so we can exercise the
    # lifecycle's one legal LOST -> PENDING_EVALUATION reopen path.
    from buyback.routes._shared import service, records_repo
    rec = records_repo.get_by_id(rid)
    rec = service.transition(rec, 'INITIAL_OFFER', actor=1)
    service.transition(rec, 'LOST', actor=1)

    r = client.post(f'/api/buyback/records/{rid}/reopen')
    assert r.status_code == 200
    assert r.get_json()['record']['status'] == 'PENDING_EVALUATION'


def test_reopen_illegal_transition_is_409(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    # Still PENDING_EVALUATION -> PENDING_EVALUATION is not a legal transition.
    r = client.post(f'/api/buyback/records/{rid}/reopen')
    assert r.status_code == 409


# ── DELETE ───────────────────────────────────────────────────────────────

def test_delete_removes_record(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert client.get(f'/api/buyback/records/{rid}').status_code == 404


def test_delete_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    as_role('Sales', 2)
    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 403


def test_delete_requires_delete_permission(client, as_role):
    """Sales role has no record.delete grant at all (module-level 403 from
    the v2_permission_required decorator, before _guard_company even runs)."""
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 403


def test_delete_missing_404(client, as_role):
    as_role('Admin', 1)
    r = client.delete('/api/buyback/records/999999999')
    assert r.status_code == 404


# ── CREATE — oversized base64 image payload ─────────────────────────────

def test_create_with_oversized_images_returns_413(client, as_role, monkeypatch):
    """Real 12MB base64 payloads are impractical in a unit test, so per the
    binding conventions we shrink the cap (monkeypatch _shared.MAX_CREATE_BYTES)
    instead of inflating the payload. spaces_service.upload is also
    monkeypatched so no real network call happens on the (unreachable, given
    the cap) upload path."""
    import buyback.routes._shared as shared
    monkeypatch.setattr(shared, 'MAX_CREATE_BYTES', 10)
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct: key,
    )

    as_role('Admin', 1)
    raw = os.urandom(100)
    data_url = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
    r = client.post('/api/buyback/records', json=_payload(images=[data_url]))
    assert r.status_code in (413, 400)


def test_create_filters_blank_image_entries(client, as_role, monkeypatch):
    """Empty/None entries in `images` must be dropped before reaching
    PhotoRepository.store_base64_images (T6 carry-forward: it has no guard
    for falsy entries and would TypeError on len(None))."""
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct: key,
    )
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(images=['', None]))
    assert r.status_code == 201, r.get_json()


def test_create_rejects_non_list_images(client, as_role):
    """A malformed `images` value (e.g. a string) must 400, not fall through
    to PhotoRepository with each character treated as a bogus 'image'."""
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(images='not-a-list'))
    assert r.status_code == 400


# ── FIX ROUND 1: tenant-boundary unification, fail-closed scoping, 413 rollback

def test_out_of_scope_company_mutation_forbidden(client, as_role, monkeypatch):
    """The mutate boundary must EQUAL the read boundary: a caller whose
    permitted-company set is {1} (e.g. a Manager org-responsible only for
    company 1) must be 403'd on PUT and DELETE of a company-2 record it could
    not LIST — no admin-ish role-name shortcut may bypass this.

    The org-responsibility mapping is simulated by monkeypatching
    `_shared._permitted_company_ids` to {1} (the coordinator's blessed
    fallback — seeding a real Sincron responsable mapping in the shared DB is
    impractical). We authenticate as Admin purely so the
    @v2_permission_required('...','edit'/'delete') decorator passes (Manager
    lacks seeded buyback role_permissions_v2 in the bare test schema); the
    behavior under test is _guard_company's boundary, which now depends solely
    on the (monkeypatched) permitted set, not the role name."""
    import buyback.routes._shared as shared
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {1})

    as_role('Admin', 1)
    foreign = shared.records_repo.create({
        'record_code': f'BB-FOREIGN-{os.urandom(4).hex()}',
        'company_id': 2, 'vin': _vin(), 'brand': 'X', 'model': 'Y',
        'created_by': 1, 'status': 'PENDING_EVALUATION',
    })
    try:
        put = client.put(f"/api/buyback/records/{foreign['id']}", json={'mileage_km': 1})
        assert put.status_code == 403, put.get_json()
        dele = client.delete(f"/api/buyback/records/{foreign['id']}")
        assert dele.status_code == 403, dele.get_json()
    finally:
        shared.records_repo.delete(foreign['id'])


def test_in_scope_company_mutation_allowed_with_bounded_set(client, as_role, monkeypatch):
    """Counterpart to the above: the same bounded permitted set {1} must ALLOW
    mutating a company-1 record (proves the 403 above is the boundary at work,
    not a blanket block)."""
    import buyback.routes._shared as shared
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {1})

    as_role('Admin', 1)
    own = shared.records_repo.create({
        'record_code': f'BB-OWN-{os.urandom(4).hex()}',
        'company_id': 1, 'vin': _vin(), 'brand': 'X', 'model': 'Y',
        'created_by': 1, 'status': 'PENDING_EVALUATION',
    })
    try:
        put = client.put(f"/api/buyback/records/{own['id']}", json={'mileage_km': 7})
        assert put.status_code == 200, put.get_json()
        assert put.get_json()['record']['mileage_km'] == 7
    finally:
        shared.records_repo.delete(own['id'])


def test_company_less_own_scope_user_sees_no_records(client, as_role):
    """Fail-closed: a company-less own-scope caller must receive NONE of any
    other company's records from GET /records — never fall through to an
    unfiltered (all-companies) list."""
    # Seed a company-1 record that WOULD leak if the list fell through to
    # company_id=None (= all companies).
    as_role('Admin', 1)
    leaked = client.post('/api/buyback/records', json=_payload()).get_json()['record']

    # A company-less Sales user (own scope, company_id=None).
    as_role('Sales', None)
    body = client.get('/api/buyback/records').get_json()
    assert body['total'] == 0
    assert body['records'] == []
    assert all(rec['id'] != leaked['id'] for rec in body['records'])


def test_company_less_own_scope_user_cannot_create(client, as_role):
    """Fail-closed on CREATE too: a company-less non-'all' caller gets 403,
    not a 500 from a NOT NULL company_id violation."""
    as_role('Sales', None)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 403


def test_create_oversized_images_rolls_back_record(client, as_role, monkeypatch):
    """A 413 (oversized image batch) must leave NO ghost record: the
    just-inserted row is rolled back before the 413 is returned."""
    import buyback.routes._shared as shared
    monkeypatch.setattr(shared, 'MAX_CREATE_BYTES', 10)
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct: key,
    )
    as_role('Admin', 1)
    vin = _vin()
    raw = os.urandom(100)
    data_url = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
    r = client.post('/api/buyback/records', json=_payload(vin=vin, images=[data_url]))
    assert r.status_code == 413

    # No ghost row for the attempted VIN.
    _rows, total = shared.records_repo.list(company_id=1, q=vin, per_page=100)
    assert total == 0


# ═══════════════════════════════════════════════════════════════════════
# FINAL REVIEW PASS: read-IDOR guard (C1), delete guard (I2), intake
# validation (I3), image-src + base64 hardening (M5/M7)
# ═══════════════════════════════════════════════════════════════════════

# ── C1 — CRITICAL cross-tenant READ IDOR (two paths) ─────────────────────

def test_get_detail_forbidden_for_bounded_all_scope_non_admin(client, as_role, monkeypatch):
    """get_record used to only call _guard_company when
    g.permission_scope != 'all', so ANY 'all'-scope caller who ISN'T a true
    global admin (Manager/Acquisition/Service are all seeded 'all' scope per
    migrations/domains/schema_roles.py) could read ANY company's record
    detail (seller PII, offer amounts, purchase price) by id enumeration.

    Simulate that caller the same way test_out_of_scope_company_mutation_
    forbidden does: authenticate as Admin (so the module-level
    @v2_permission_required('...','view') passes and g.permission_scope is
    really 'all'), then monkeypatch _permitted_company_ids to a bounded set
    that excludes the foreign record's company — this is the IDOR boundary
    _guard_company must now enforce unconditionally."""
    import buyback.routes._shared as shared
    as_role('Admin', 1)
    foreign = shared.records_repo.create({
        'record_code': f'BB-FOREIGN-{os.urandom(4).hex()}',
        'company_id': 2, 'vin': _vin(), 'brand': 'X', 'model': 'Y',
        'created_by': 1, 'status': 'PENDING_EVALUATION',
    })
    try:
        monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {1})
        r = client.get(f"/api/buyback/records/{foreign['id']}")
        assert r.status_code == 403, r.get_json()
    finally:
        shared.records_repo.delete(foreign['id'])


def test_get_detail_global_admin_reads_any_company_regression(client, as_role):
    """Regression guard: a TRUE global admin (can_access_settings ->
    _permitted_company_ids() is the unrestricted None sentinel) must still
    be able to read a record belonging to a company OTHER than the one
    they're currently acting as — the unconditional _guard_company call
    must not have broken the global-admin bypass."""
    as_role('Admin', 2)
    foreign = client.post('/api/buyback/records', json=_payload()).get_json()['record']
    assert foreign['company_id'] == 2

    as_role('Admin', 1)
    r = client.get(f"/api/buyback/records/{foreign['id']}")
    assert r.status_code == 200
    assert r.get_json()['record']['id'] == foreign['id']


def test_list_bounded_all_scope_company_less_caller_gets_empty_page(client, as_role, monkeypatch):
    """list_records' old empty-page guard only fired for
    g.permission_scope != 'all', so a bounded 'all'-scope caller (real role
    scope 'all', but NOT can_access_settings) whose permitted set doesn't
    include any company fell straight through to
    RecordRepository.list(company_id=None) — i.e. every tenant's records.
    Seed a company-1 record that WOULD leak under the old behavior, then
    read the list back as that bounded, company-less caller."""
    import buyback.routes._shared as shared
    as_role('Admin', 1)
    leaked = client.post('/api/buyback/records', json=_payload()).get_json()['record']

    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: set())
    body = client.get('/api/buyback/records').get_json()
    assert body['total'] == 0
    assert body['records'] == []
    assert all(rec['id'] != leaked['id'] for rec in body['records'])


def test_list_bounded_all_scope_out_of_set_company_param_gets_empty_page(client, as_role, monkeypatch):
    """A bounded 'all'-scope caller explicitly requesting a company_id
    OUTSIDE their permitted set must also get an empty page — never that
    other company's records."""
    import buyback.routes._shared as shared
    as_role('Admin', 1)
    other = shared.records_repo.create({
        'record_code': f'BB-OTHER-{os.urandom(4).hex()}',
        'company_id': 2, 'vin': _vin(), 'brand': 'X', 'model': 'Y',
        'created_by': 1, 'status': 'PENDING_EVALUATION',
    })
    try:
        monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {1})
        body = client.get('/api/buyback/records?company_id=2').get_json()
        assert body['total'] == 0
        assert body['records'] == []
    finally:
        shared.records_repo.delete(other['id'])


def test_list_global_admin_lists_any_company_regression(client, as_role):
    """Regression guard: a TRUE global admin's LIST stays unrestricted —
    an explicit ?company_id filter for a company other than the one
    they're currently acting as still returns that company's records."""
    as_role('Admin', 3)
    rec = client.post('/api/buyback/records', json=_payload()).get_json()['record']

    as_role('Admin', 1)
    body = client.get('/api/buyback/records?company_id=3').get_json()
    assert any(r['id'] == rec['id'] for r in body['records'])


# ── I2 — delete must not hard-delete financial/terminal records ─────────

def test_delete_refuses_bought_record(client, as_role):
    """A BOUGHT record's audit trail (and its CarPark vehicle back-link)
    must never be destroyed by a delete — refuse with 409 and keep the
    row."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    from buyback.routes._shared import service, records_repo
    rec = records_repo.get_by_id(rid)
    rec = service.transition(rec, 'INITIAL_OFFER', actor=1)
    rec = service.transition(rec, 'INSPECTION', actor=1)
    rec = service.transition(rec, 'FINAL_OFFER', actor=1)
    service.transition(rec, 'BOUGHT', actor=1)

    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 409, r.get_json()
    assert records_repo.get_by_id(rid) is not None


def test_delete_refuses_when_carpark_vehicle_linked_even_if_status_deletable(client, as_role):
    """Belt-and-suspenders half of the guard: a carpark_vehicle_id link
    blocks delete even for an otherwise-deletable status (PENDING_EVALUATION
    here) — a record must never be deletable once it carries a CarPark
    back-link, regardless of how it got one."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    from buyback.routes._shared import records_repo
    records_repo.update(rid, {'carpark_vehicle_id': 999999})

    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 409, r.get_json()
    assert records_repo.get_by_id(rid) is not None


def test_delete_allows_pending_evaluation_record(client, as_role):
    """Counterpart to the BOUGHT refusal: an untouched PENDING_EVALUATION
    record is still freely deletable (already covered by
    test_delete_removes_record above; kept here alongside the CANCELLED/LOST
    cases so all three "deletable" statuses are exercised together)."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 200
    from buyback.routes._shared import records_repo
    assert records_repo.get_by_id(rid) is None


def test_delete_allows_cancelled_record(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    cancel = client.post(f'/api/buyback/records/{rid}/cancel', json={'reason': 'x'})
    assert cancel.status_code == 200, cancel.get_json()

    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 200, r.get_json()
    from buyback.routes._shared import records_repo
    assert records_repo.get_by_id(rid) is None


def test_delete_allows_lost_record(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    from buyback.routes._shared import service, records_repo
    rec = records_repo.get_by_id(rid)
    rec = service.transition(rec, 'INITIAL_OFFER', actor=1)
    service.transition(rec, 'LOST', actor=1)

    r = client.delete(f'/api/buyback/records/{rid}')
    assert r.status_code == 200, r.get_json()
    assert records_repo.get_by_id(rid) is None


# ── I3 — create/update intake type validation (400, never 500) ──────────

def test_create_bad_mileage_type_is_400_not_500(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(mileage_km='abc'))
    assert r.status_code == 400
    assert r.status_code != 500


def test_create_bad_manufacture_date_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(manufacture_date='2020-13-99'))
    assert r.status_code == 400


def test_create_non_scalar_other_details_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(other_details={'a': 1}))
    assert r.status_code == 400


def test_create_out_of_range_general_condition_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(general_condition=9))
    assert r.status_code == 400


def test_create_negative_keys_count_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(keys_count=-1))
    assert r.status_code == 400


def test_create_bad_asking_price_type_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(client_asking_price_eur='not-a-number'))
    assert r.status_code == 400


def test_create_missing_brand_is_400(client, as_role):
    as_role('Admin', 1)
    data = _payload()
    data.pop('brand')
    r = client.post('/api/buyback/records', json=data)
    assert r.status_code == 400


def test_create_missing_model_is_400(client, as_role):
    as_role('Admin', 1)
    data = _payload()
    data.pop('model')
    r = client.post('/api/buyback/records', json=data)
    assert r.status_code == 400


def test_create_blank_brand_is_400(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(brand='   '))
    assert r.status_code == 400


def test_create_valid_payload_with_all_intake_types_still_201(client, as_role):
    """Regression guard: a fully-populated, well-typed payload still creates
    successfully and the validator's coercions (bool/int/Decimal) round-trip
    correctly."""
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(
        mileage_km=50000, general_condition=4, keys_count=2,
        client_asking_price_eur=1234.56, manufacture_date='2020-01-15',
        has_damage=True, is_trade_in='false',
    ))
    assert r.status_code == 201, r.get_json()
    rec = r.get_json()['record']
    assert rec['mileage_km'] == 50000
    assert rec['has_damage'] is True
    assert rec['is_trade_in'] is False


def test_update_bad_type_is_400(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'general_condition': 9})
    assert r.status_code == 400


def test_update_non_scalar_field_is_400(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'damage_details': ['x']})
    assert r.status_code == 400


def test_update_blank_brand_is_400(client, as_role):
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'brand': ''})
    assert r.status_code == 400


def test_update_omitted_brand_model_still_ok(client, as_role):
    """UPDATE only requires brand/model non-empty WHEN present — a partial
    update that omits both entirely must not be rejected."""
    as_role('Admin', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    r = client.put(f'/api/buyback/records/{rid}', json={'mileage_km': 999})
    assert r.status_code == 200, r.get_json()


# ── M5 — base64 images[] restricted to data: URLs ────────────────────────

def test_create_rejects_bare_key_image_entry_no_spaces_fetch(client, as_role, monkeypatch):
    """A bare string in images[] must NOT be treated as an existing Spaces
    object key — resolve_image_bytes() would otherwise fetch() it, letting a
    caller copy another tenant's private object (e.g. another company's
    carpark photo) into their own gallery just by naming its key. Assert a
    400 AND that no Spaces fetch ever happens."""
    from core.services import spaces_service
    calls = []
    monkeypatch.setattr(
        spaces_service, 'fetch',
        lambda key: (calls.append(key), (b'x', 'image/jpeg'))[1],
    )
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(images=['private/carpark/1/x.jpg']))
    assert r.status_code == 400, r.get_json()
    assert calls == []


# ── M7 — malformed base64 is 400, not a misleading 413 ───────────────────

def test_create_malformed_base64_is_400_not_413(client, as_role, monkeypatch):
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct: key,
    )
    as_role('Admin', 1)
    r = client.post('/api/buyback/records', json=_payload(
        images=['data:image/jpeg;base64,@@@notbase64@@@'],
    ))
    assert r.status_code == 400, r.get_json()


def test_create_oversized_images_is_exactly_413(client, as_role, monkeypatch):
    """Regression guard, stricter than the pre-existing
    test_create_with_oversized_images_returns_413 (which accepted 413 OR 400
    to stay agnostic about the eventual malformed-vs-oversized split): after
    M7's except-split, a genuinely oversized (well-formed) batch must be
    exactly 413, never 400."""
    import buyback.routes._shared as shared
    monkeypatch.setattr(shared, 'MAX_CREATE_BYTES', 10)
    monkeypatch.setattr(
        'buyback.repositories.photo_repository.spaces_service.upload',
        lambda data, key, ct: key,
    )
    as_role('Admin', 1)
    raw = os.urandom(100)
    data_url = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
    r = client.post('/api/buyback/records', json=_payload(images=[data_url]))
    assert r.status_code == 413, r.get_json()
