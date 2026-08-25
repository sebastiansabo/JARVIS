"""Tests for the Foi de Parcurs analytics endpoint GET /api/foi-parcurs/reports/summary.

The security-critical behaviour lives in the route (not the SQL): company-scope
enforcement and the rental-only-on-Service gate. Those are exercised here with a
minimal Flask app registering foi_parcurs_bp, with _fp_repo/_vehicle_repo/
current_user monkeypatched at the module level (mirrors test_td_company_gate.py).

Scope rule (role-scoped, "Both"):
  * Group viewers (admin / superadmin / board) may report on ANY company_id, or
    omit it for the whole group (company_id=None → all companies).
  * Everyone else is forced to their OWN company_id regardless of what they pass
    (aggregated business metrics are a hard boundary, unlike the group-wide row
    lists). A non-group user with no company_id on file is denied (403).

Rental rule: "Venit închiriere" exists only on the Service pool, so report_rental
is queried (and present in the payload) ONLY when document_type == 'service'.

The aggregate SQL itself (report_bundle / report_fleet / report_rental bodies) is
validated separately against the live dev DB — pytest mocks psycopg2, so SQL can't
run here.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.reports as rep_mod


class FakeUser:
    def __init__(self, role_name='user', company_id=None):
        self.role_name = role_name
        self.company_id = company_id
        self.name = 'Tester'
        self.email = 't@e.ro'


BUNDLE = {
    'kpis': {'total_sessions': 10, 'total_km': 500, 'cars_used': 4,
             'avg_km_per_session': 50, 'completion_rate': 90, 'test_drives': 6},
    'sessions_over_time': [{'bucket': '2026-08-01', 'count': 3}],
    'by_status': [{'status': 'complete', 'count': 8}],
    'by_type': [{'type': 'test_drive', 'count': 6}],
    'client_vs_internal': [{'segment': 'client', 'count': 7}, {'segment': 'internal', 'count': 3}],
    'by_brand': [{'brand': 'Volkswagen', 'count': 4}],
    'client_types': [{'client_type': 'company', 'count': 5}],
    'top_clients': [{'client': 'ACME', 'sessions': 3}],
    'top_advisors': [{'advisor': 'Ion', 'sessions': 5}],
    'top_companies': [{'company_id': 11, 'company': 'Autoworld', 'sessions': 9}],
    'utilization': [{'vin': 'V1', 'days_used': 5, 'sessions': 3, 'km': 200}],
    'distance_by_brand': [{'brand': 'Volvo', 'km': 300}],
}
FLEET = {
    'fuel_composition': [{'fuel_type': 'Diesel', 'count': 20}],
    'top_odometer': [{'vin': 'V1', 'registration_number': 'B 01 AAA', 'odometer_km': 120000}],
}
RENTAL = {'total_eur': 6820, 'by_month': [{'bucket': '2026-08', 'eur': 6820}], 'sessions': 12}


SESSIONS = [{'id': 1, 'date': '2026-08-10', 'client': 'ACME', 'advisor': 'Ion',
             'vin': 'V1', 'registration_number': 'B 01 AAA', 'model': 'VW Passat',
             'td_status': 'complete', 'km': 42}]


class FakeFp:
    def __init__(self):
        self.bundle_args = None
        self.rental_args = None
        self.sessions_args = None

    def report_bundle(self, company_id=None, date_from=None, date_to=None, document_type=None, top=5,
                      perf_status=None, drive_type=None, brand=None):
        self.bundle_args = dict(company_id=company_id, date_from=date_from, date_to=date_to,
                                document_type=document_type, top=top,
                                perf_status=perf_status, drive_type=drive_type, brand=brand)
        return dict(BUNDLE)

    def report_rental(self, company_id=None, date_from=None, date_to=None, brand=None):
        self.rental_args = dict(company_id=company_id, date_from=date_from, date_to=date_to, brand=brand)
        return dict(RENTAL)

    def report_sessions(self, company_id=None, date_from=None, date_to=None,
                        document_type=None, advisor=None, vin=None, limit=200,
                        status=None, drive_type=None, client_type=None, brand=None, fuel_type=None):
        self.sessions_args = dict(company_id=company_id, date_from=date_from, date_to=date_to,
                                  document_type=document_type, advisor=advisor, vin=vin, limit=limit,
                                  status=status, drive_type=drive_type,
                                  client_type=client_type, brand=brand, fuel_type=fuel_type)
        return list(SESSIONS)


class FakeVeh:
    def __init__(self):
        self.fleet_args = None

    def report_fleet(self, company_id=None, document_type=None, odo_order='high', top=5, brand=None):
        self.fleet_args = dict(company_id=company_id, document_type=document_type,
                               odo_order=odo_order, top=top, brand=brand)
        return dict(FLEET)


def make_client(monkeypatch, role='user', company_id=None):
    fake_fp = FakeFp()
    fake_veh = FakeVeh()
    monkeypatch.setattr(rep_mod, '_fp_repo', fake_fp)
    monkeypatch.setattr(rep_mod, '_vehicle_repo', fake_veh)
    monkeypatch.setattr(rep_mod, 'current_user', FakeUser(role, company_id))
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    tc = app.test_client()
    tc._fp = fake_fp
    tc._veh = fake_veh
    return tc


def test_non_admin_forced_to_own_company(monkeypatch):
    """A non-group user requesting ?company_id=99 is silently scoped to their own
    company (11) — the requested id is ignored, not honored (IDOR guard)."""
    c = make_client(monkeypatch, role='user', company_id=11)
    r = c.get('/api/foi-parcurs/reports/summary?company_id=99&document_type=sales')
    assert r.status_code == 200, r.get_json()
    assert c._fp.bundle_args['company_id'] == 11
    assert c._veh.fleet_args['company_id'] == 11
    body = r.get_json()
    assert body['scope']['company_id'] == 11
    assert body['scope']['is_group'] is False


def test_admin_all_companies_when_no_company_id(monkeypatch):
    """A group viewer (admin) with no company_id param reports across the whole
    group (company_id passed to the repo as None)."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales')
    assert r.status_code == 200
    assert c._fp.bundle_args['company_id'] is None
    assert r.get_json()['scope']['is_group'] is True


def test_admin_can_scope_to_specific_company(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?company_id=99&document_type=sales')
    assert r.status_code == 200
    assert c._fp.bundle_args['company_id'] == 99


def test_board_is_group_viewer(monkeypatch):
    c = make_client(monkeypatch, role='board', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?company_id=99&document_type=sales')
    assert r.status_code == 200
    assert c._fp.bundle_args['company_id'] == 99
    assert r.get_json()['scope']['is_group'] is True


def test_non_admin_without_company_denied(monkeypatch):
    c = make_client(monkeypatch, role='user', company_id=None)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales')
    assert r.status_code == 403


def test_rental_absent_on_sales(monkeypatch):
    """On the Sales pool there is no rental revenue — the block is None and the
    (potentially expensive) rental query is never even run."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales')
    assert r.get_json()['rental'] is None
    assert c._fp.rental_args is None


def test_rental_present_on_service(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=service')
    body = r.get_json()
    assert body['rental'] is not None
    assert body['rental']['total_eur'] == 6820
    assert c._fp.rental_args is not None


def test_response_contains_all_blocks(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales')
    body = r.get_json()
    for key in ('kpis', 'sessions_over_time', 'by_status', 'by_type', 'client_vs_internal',
                'by_brand', 'client_types', 'top_clients', 'top_advisors', 'top_companies',
                'utilization', 'distance_by_brand', 'fuel_composition', 'top_odometer',
                'rental', 'scope'):
        assert key in body, f'missing block: {key}'
    assert body['success'] is True


def test_client_vs_internal_block_shape(monkeypatch):
    """The dedicated Client-vs-Intern split is a two-segment breakdown."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales')
    segs = {row['segment'] for row in r.get_json()['client_vs_internal']}
    assert segs == {'client', 'internal'}


def test_filters_passed_through(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary'
              '?document_type=service&date_from=2026-08-01&date_to=2026-08-25&odo_order=low&top=8')
    assert r.status_code == 200
    a = c._fp.bundle_args
    assert a['date_from'] == '2026-08-01'
    assert a['date_to'] == '2026-08-25'
    assert a['document_type'] == 'service'
    assert a['top'] == 8
    assert c._veh.fleet_args['odo_order'] == 'low'
    assert c._veh.fleet_args['top'] == 8


# ── drill-down: /reports/sessions ──────────────────────────────────────────

def test_sessions_forced_to_own_company_for_non_admin(monkeypatch):
    """The drill-down enforces the same hard company scope — a non-group user's
    ?company_id is ignored in favour of their own company (no cross-tenant peek)."""
    c = make_client(monkeypatch, role='user', company_id=11)
    r = c.get('/api/foi-parcurs/reports/sessions?company_id=99&advisor=Ion&document_type=sales')
    assert r.status_code == 200, r.get_json()
    assert c._fp.sessions_args['company_id'] == 11
    assert c._fp.sessions_args['advisor'] == 'Ion'


def test_sessions_requires_advisor_or_vin(monkeypatch):
    """With neither advisor nor vin there is nothing to drill into — return an
    empty list without touching the repo."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/sessions?document_type=sales')
    assert r.status_code == 200
    assert r.get_json()['sessions'] == []
    assert c._fp.sessions_args is None


def test_sessions_vin_and_filters_passthrough(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/sessions?vin=WVW1&date_from=2026-08-01&document_type=service')
    assert r.status_code == 200
    a = c._fp.sessions_args
    assert a['vin'] == 'WVW1'
    assert a['document_type'] == 'service'
    assert a['date_from'] == '2026-08-01'
    assert r.get_json()['sessions'][0]['client'] == 'ACME'


def test_sessions_non_admin_without_company_denied(monkeypatch):
    c = make_client(monkeypatch, role='user', company_id=None)
    r = c.get('/api/foi-parcurs/reports/sessions?advisor=Ion')
    assert r.status_code == 403


def test_summary_status_and_drive_type_passthrough(monkeypatch):
    """The performance status filter + general client/intern filter reach the repo."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=sales&status=complete&drive_type=internal')
    assert r.status_code == 200
    assert c._fp.bundle_args['perf_status'] == 'complete'
    assert c._fp.bundle_args['drive_type'] == 'internal'


def test_summary_brand_isolates_whole_report(monkeypatch):
    """The header brand selector isolates every block (bundle + fleet + rental)."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/summary?document_type=service&brand=MG Motor')
    assert r.status_code == 200
    assert c._fp.bundle_args['brand'] == 'MG Motor'
    assert c._veh.fleet_args['brand'] == 'MG Motor'
    assert c._fp.rental_args['brand'] == 'MG Motor'


def test_sessions_status_and_drive_type_passthrough(monkeypatch):
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/sessions?advisor=Ion&status=missed&drive_type=client')
    assert r.status_code == 200
    assert c._fp.sessions_args['status'] == 'missed'
    assert c._fp.sessions_args['drive_type'] == 'client'


def test_sessions_chart_dimension_filters_passthrough(monkeypatch):
    """Chart detail modals drill by client_type / brand / fuel_type."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/sessions?fuel_type=Benzina&brand=Audi&client_type=company')
    assert r.status_code == 200
    a = c._fp.sessions_args
    assert a['fuel_type'] == 'Benzina'
    assert a['brand'] == 'Audi'
    assert a['client_type'] == 'company'


def test_sessions_multi_status_cumulates(monkeypatch):
    """Checkbox status filter sends a comma-separated set that reaches the repo."""
    c = make_client(monkeypatch, role='admin', company_id=16)
    r = c.get('/api/foi-parcurs/reports/sessions?vin=WVW1&status=complete,missed')
    assert r.status_code == 200
    assert c._fp.sessions_args['status'] == 'complete,missed'
