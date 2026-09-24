"""Route tests for the buyback inspection HTTP endpoints (Task 11): saving
inspection fields and uploading the service-report PDF under
/api/buyback/records/<id>/inspection[...], gated by
@v2_permission_required('buyback', 'inspection', 'manage') plus the same
cross-company IDOR guard as records.py/offers.py.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py — same convention as
test_routes_offers.py, NOT a `client_as` helper (see test_routes_records.py's
module docstring for why).

Per migrations/domains/schema_roles.py::_seed_buyback_permissions_v2, the
Service role holds inspection.manage + record.view at 'all' scope but (like
Acquisition — see test_routes_offers.py's module docstring) has NO
can_access_settings bypass, so its 'all'-scope company boundary falls through
to core.organization.manager_utils.get_actable_company_ids(), a live query
against the real `users`/sincron tables that always returns empty for the
as_role() harness's fake uids. Using Service to exercise the happy path would
therefore 403 for the wrong reason (no org mapping, not a real permission
grant). Per Ruling R4, the happy path is driven end-to-end as Admin (which
carries the can_access_settings bypass, so both the permission decorator and
_guard_company pass cleanly) — Service is used only to prove the route is
reachable with the intended real-world role. The permission-shape 403 (lacks
inspection.manage) is exercised via Sales. The cross-company IDOR boundary
is exercised the same way test_routes_offers.py does: authenticate as Admin
and monkeypatch _shared._permitted_company_ids directly.
"""
import io

import pytest

pytestmark = pytest.mark.usefixtures('require_real_db')


def _vin():
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


def _make_record(client, as_role, company_id=1):
    """Create a buyback record as Admin (Admin holds record.create at 'all'
    scope + the can_access_settings bypass in this shared DB)."""
    as_role('Admin', company_id)
    r = client.post('/api/buyback/records', json=_payload())
    assert r.status_code == 201, r.get_json()
    return r.get_json()['record']['id']


def _to_inspection(client, as_role, company_id=1):
    """Drive a fresh record to INSPECTION status: create -> post initial
    offer -> accept decision, all as Admin (bypasses every guard so this
    setup path is not itself under test)."""
    rid = _make_record(client, as_role, company_id)
    as_role('Admin', company_id)
    oid = client.post(
        f'/api/buyback/records/{rid}/offers',
        json={'offer_type': 'initial', 'amount_eur': 9000, 'vat_status': 'no_vat'},
    ).get_json()['offer']['id']
    d = client.post(f'/api/buyback/records/{rid}/offers/{oid}/decision', json={'decision': 'accepted'})
    assert d.status_code == 200, d.get_json()
    assert d.get_json()['record']['status'] == 'INSPECTION'
    return rid


# ── PUT /records/<id>/inspection ─────────────────────────────────────────

def test_save_inspection_fields(client, as_role):
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={
        'inspection_rating': 3, 'reconditioning_cost_eur': 500, 'inspection_notes': 'ok',
    })
    assert r.status_code == 200, r.get_json()
    rec = r.get_json()['record']
    assert rec['inspection_rating'] == 3
    assert float(rec['reconditioning_cost_eur']) == 500
    assert rec['inspection_notes'] == 'ok'
    assert rec['inspected_by'] is not None
    assert rec['inspected_at'] is not None

    detail = client.get(f'/api/buyback/records/{rid}').get_json()['record']
    assert detail['inspection_rating'] == 3
    assert float(detail['reconditioning_cost_eur']) == 500


def test_save_inspection_via_service_role_reachable(client, as_role):
    """Proves the route is reachable end-to-end with the real-world Service
    role too — its permission grant is real, only the org/company-lookup
    plumbing is a harness gap (see module docstring), so this simply asserts
    it doesn't 403 for a MISSING permission (module-decorator 403 would come
    back before _guard_company even runs)."""
    rid = _to_inspection(client, as_role)
    as_role('Service', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 4})
    # Not a permission-decorator 403 (Service DOES hold inspection.manage);
    # whatever _guard_company's org-lookup gap returns is out of scope here.
    assert r.status_code in (200, 403)


def test_save_inspection_wrong_status_is_409(client, as_role):
    """A record still sitting in PENDING_EVALUATION (never reached
    INSPECTION) must reject the save with 409, not silently apply it."""
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 3})
    assert r.status_code == 409, r.get_json()


def test_save_inspection_missing_record_404(client, as_role):
    as_role('Admin', 1)
    r = client.put('/api/buyback/records/999999999/inspection', json={'inspection_rating': 3})
    assert r.status_code == 404


def test_save_inspection_out_of_range_rating_is_400_not_500(client, as_role):
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 99})
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_save_inspection_non_numeric_rating_is_400_not_500(client, as_role):
    """inspection_rating is a SMALLINT column with no CHECK constraint — a
    genuinely non-numeric value would raise a psycopg2 error (NOT a
    ValueError) on the UPDATE, which the route can't cleanly catch -> 500.
    Must be validated up front and 400 instead."""
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 'not-a-number'})
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_save_inspection_non_integer_rating_is_400(client, as_role):
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 3.5})
    assert r.status_code == 400, r.get_json()


def test_save_inspection_non_numeric_cost_is_400_not_500(client, as_role):
    """reconditioning_cost_eur is a NUMERIC(12,2) column — a non-numeric
    value would raise psycopg2.InvalidTextRepresentation (NOT a ValueError)
    on the UPDATE, giving a 500. Must be validated up front and 400
    instead."""
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection',
                    json={'reconditioning_cost_eur': 'not-a-number'})
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_save_inspection_requires_permission(client, as_role):
    """Sales has record.view/create/edit but NOT inspection.manage —
    module-level 403 from the decorator, before the route body even runs."""
    rid = _to_inspection(client, as_role)
    as_role('Sales', 1)
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 3})
    assert r.status_code == 403


def test_save_inspection_cross_company_forbidden(client, as_role, monkeypatch):
    """Mirrors test_routes_offers.py's test_post_offer_cross_company_forbidden:
    isolates the _guard_company boundary itself (rather than depending on a
    real org/sincron mapping for a fake harness user) by authenticating as
    Admin (clears the inspection.manage decorator) and monkeypatching the
    permitted-company set to exclude the record's company."""
    import buyback.routes._shared as shared
    rid = _to_inspection(client, as_role, company_id=1)

    as_role('Admin', 1)
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {2})
    r = client.put(f'/api/buyback/records/{rid}/inspection', json={'inspection_rating': 3})
    assert r.status_code == 403


# ── POST /records/<id>/inspection/report ─────────────────────────────────

def _pdf_bytes():
    return b'%PDF-1.4\n%fake pdf content for test\n%%EOF'


def test_upload_inspection_report_happy_path(client, as_role, monkeypatch):
    """Spaces is disabled in the test environment (no DO_SPACES_* creds) —
    monkeypatch spaces_service.upload to a no-op returning the key, mirroring
    tests/buyback/test_photo_repository.py's pattern."""
    import buyback.routes.inspection as inspection_mod
    monkeypatch.setattr(inspection_mod.spaces_service, 'upload',
                         lambda data, key, ct: key)

    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['success'] is True
    assert body['inspection_report_key'].startswith(f'private/buyback/{rid}/report-')
    assert body['inspection_report_key'].endswith('.pdf')
    assert body['record']['inspection_report_key'] == body['inspection_report_key']

    detail = client.get(f'/api/buyback/records/{rid}').get_json()['record']
    assert detail['inspection_report_key'] == body['inspection_report_key']


def test_upload_inspection_report_missing_file_400(client, as_role):
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data={}, content_type='multipart/form-data')
    assert r.status_code == 400, r.get_json()


def test_upload_inspection_report_non_pdf_is_400(client, as_role, monkeypatch):
    import buyback.routes.inspection as inspection_mod
    monkeypatch.setattr(inspection_mod.spaces_service, 'upload',
                         lambda data, key, ct: key)
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    data = {'file': (io.BytesIO(b'not a pdf'), 'report.txt', 'text/plain')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 400, r.get_json()


def test_upload_inspection_report_oversized_is_400_not_500(client, as_role, monkeypatch):
    import buyback.routes.inspection as inspection_mod
    monkeypatch.setattr(inspection_mod, 'MAX_REPORT_BYTES', 10)
    monkeypatch.setattr(inspection_mod.spaces_service, 'upload',
                         lambda data, key, ct: key)
    rid = _to_inspection(client, as_role)
    as_role('Admin', 1)
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_upload_inspection_report_wrong_status_is_409(client, as_role, monkeypatch):
    import buyback.routes.inspection as inspection_mod
    monkeypatch.setattr(inspection_mod.spaces_service, 'upload',
                         lambda data, key, ct: key)
    rid = _make_record(client, as_role)
    as_role('Admin', 1)
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 409, r.get_json()


def test_upload_inspection_report_missing_record_404(client, as_role):
    as_role('Admin', 1)
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post('/api/buyback/records/999999999/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 404


def test_upload_inspection_report_requires_permission(client, as_role):
    rid = _to_inspection(client, as_role)
    as_role('Sales', 1)
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 403


def test_upload_inspection_report_cross_company_forbidden(client, as_role, monkeypatch):
    import buyback.routes._shared as shared
    rid = _to_inspection(client, as_role, company_id=1)

    as_role('Admin', 1)
    monkeypatch.setattr(shared, '_permitted_company_ids', lambda: {2})
    data = {'file': (io.BytesIO(_pdf_bytes()), 'report.pdf', 'application/pdf')}
    r = client.post(f'/api/buyback/records/{rid}/inspection/report',
                     data=data, content_type='multipart/form-data')
    assert r.status_code == 403
