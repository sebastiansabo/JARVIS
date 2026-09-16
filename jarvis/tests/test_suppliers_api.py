from core.suppliers.routes import _check_supplier_perm


def test_perm_helper_denies_when_no_role(monkeypatch):
    import core.suppliers.routes as r
    class U:  # anonymous-ish
        is_authenticated = True
        role_id = None
        role_name = ''
    monkeypatch.setattr(r, 'current_user', U(), raising=False)
    assert _check_supplier_perm('view') is False

def test_perm_helper_uses_has_permission(monkeypatch):
    import core.suppliers.routes as r
    class U:
        is_authenticated = True
        role_id = 5
        role_name = 'Dep Contabilitate'
    monkeypatch.setattr(r, 'current_user', U(), raising=False)
    monkeypatch.setattr(r._perm_repo, 'check_permission_v2',
                        lambda *a, **k: {'has_permission': True, 'scope': 'all', 'has_explicit_entry': True})
    assert _check_supplier_perm('view') is True
    monkeypatch.setattr(r._perm_repo, 'check_permission_v2',
                        lambda *a, **k: {'has_permission': False, 'scope': 'deny', 'has_explicit_entry': True})
    assert _check_supplier_perm('edit') is False


# ── _export_format: CSV/XLSX dispatch for the general export ──

def test_export_format_resolves_xlsx():
    import core.suppliers.routes as r
    from core.suppliers.eurofib_export import build_xlsx
    mime, ext, builder = r._export_format('xlsx')
    assert ext == 'xlsx'
    assert mime == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert builder is build_xlsx


def test_export_format_is_case_insensitive():
    import core.suppliers.routes as r
    _, ext, _ = r._export_format('XLSX')
    assert ext == 'xlsx'


def test_export_format_resolves_csv_when_explicit():
    import core.suppliers.routes as r
    from core.suppliers.eurofib_export import build_csv
    mime, ext, builder = r._export_format('csv')
    assert (mime, ext, builder) == ('text/csv', 'csv', build_csv)


def test_export_format_defaults_to_xlsx_for_unknown_or_blank():
    # XLSX is the primary EuroFib format; CSV stays available as an explicit option only.
    import core.suppliers.routes as r
    from core.suppliers.eurofib_export import build_xlsx
    for fmt in (None, '', 'bogus'):
        mime, ext, builder = r._export_format(fmt)
        assert (mime, ext, builder) == (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx', build_xlsx)


# ── _to_invoice_config_pairs: valuta = invoice due date (data scadență), fallback invoice_date ──

def _fake_effective_konto(*a, **k):
    return {'konto': {'konto_debit': '628701', 'konto_credit': '40102793', 'klient': '140',
                      'steuercode': '621', 'belegart': 'JC'}}


def test_pairs_use_due_date_for_valuta_when_present(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r._repo, 'get_effective_konto', _fake_effective_konto)
    rows = [{'supplier': 'MEDLINE', 'supplier_id': 44, 'invoice_number': 'N1',
             'invoice_date': '2026-08-31', 'due_date': '2026-09-30',
             'net_value': 100, 'invoice_value': 119, 'subtract_vat': True}]
    pairs = r._to_invoice_config_pairs(rows, 11, [])
    assert pairs[0][0]['due_date'] == '2026-09-30'


def test_pairs_fall_back_to_invoice_date_without_due_date(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r._repo, 'get_effective_konto', _fake_effective_konto)
    for due in (None, ''):
        rows = [{'supplier': 'X', 'supplier_id': 1, 'invoice_number': 'N2',
                 'invoice_date': '2026-08-31', 'due_date': due,
                 'net_value': 100, 'invoice_value': 119, 'subtract_vat': True}]
        pairs = r._to_invoice_config_pairs(rows, 11, [])
        assert pairs[0][0]['due_date'] == '2026-08-31'


# ── _resolve_amounts: net/gross for EuroFib, incl. whole-value (no-VAT) invoices ──

def test_resolve_amounts_vat_invoice_uses_net_and_gross():
    import core.suppliers.routes as r
    assert r._resolve_amounts({'net_value': 100, 'invoice_value': 119, 'subtract_vat': True}) == (100, 119)


def test_resolve_amounts_whole_value_invoice_nets_to_gross():
    # Foreign reverse-charge / whole-value (subtract_vat False): net_value is NULL by design;
    # it must still export with net = gross (VAT 0), not be skipped.
    import core.suppliers.routes as r
    assert r._resolve_amounts({'net_value': None, 'invoice_value': 50, 'subtract_vat': False}) == (50, 50)


def test_resolve_amounts_vat_invoice_missing_net_is_unusable():
    import core.suppliers.routes as r
    assert r._resolve_amounts({'net_value': None, 'invoice_value': 119, 'subtract_vat': True}) == (None, None)


def test_resolve_amounts_no_gross_is_unusable():
    import core.suppliers.routes as r
    assert r._resolve_amounts({'net_value': None, 'invoice_value': None, 'subtract_vat': False}) == (None, None)


def test_resolve_amounts_gross_amount_takes_precedence():
    import core.suppliers.routes as r
    assert r._resolve_amounts({'gross_amount': 200, 'invoice_value': 119, 'net_value': 150}) == (150, 200)


# ── _import_partner: create-vs-link decision for the "Sync cu e-Factura" import ──

from core.suppliers.resolver import Resolution


class _UniqueViolation(Exception):
    """Stand-in whose class name matches _is_unique_violation's fallback check."""


class _FakeResolver:
    def __init__(self, resolution):
        self._resolution = resolution
    def resolve(self, name=None, cui=None):
        return self._resolution


class _FakeRepo:
    def __init__(self, create=42, cui_hit=None, raise_on_create=False):
        self._create, self._cui_hit, self._raise = create, cui_hit, raise_on_create
        self.aliased, self.bound = [], []
    def create_master(self, name, created_by=None, cui=None):
        if self._raise:
            raise _UniqueViolation('duplicate key')
        return self._create
    def find_by_cui_normalized(self, cui):
        return self._cui_hit
    def add_alias(self, sid, alias_name=None, alias_cui=None, source='manual', created_by=None):
        self.aliased.append((sid, alias_name, source)); return 1
    def set_efactura_supplier_id(self, sid, partner_name=None, partner_cif=None):
        self.bound.append((sid, partner_name)); return 3


def _run_import(monkeypatch, resolution, repo):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_resolver', _FakeResolver(resolution))
    monkeypatch.setattr(r, '_repo', repo)
    return r._import_partner('MEDLINE COM SRL', 'RO5996564', uid=1)


def test_import_new_partner_creates_and_binds(monkeypatch):
    repo = _FakeRepo(create=42)
    assert _run_import(monkeypatch, Resolution(None, 'none', 'none'), repo) == 'created'
    assert repo.aliased == [(42, 'MEDLINE COM SRL', 'efactura_import')]
    assert repo.bound == [(42, 'MEDLINE COM SRL')]


def test_import_existing_supplier_links_without_creating(monkeypatch):
    repo = _FakeRepo()
    assert _run_import(monkeypatch, Resolution(7, 'high', 'cui'), repo) == 'linked'
    assert repo.bound == [(7, 'MEDLINE COM SRL')]  # bound to the existing master, no create


def test_import_cui_collision_on_create_links_to_existing(monkeypatch):
    repo = _FakeRepo(raise_on_create=True, cui_hit=9)
    assert _run_import(monkeypatch, Resolution(None, 'none', 'none'), repo) == 'linked'
    assert repo.bound == [(9, 'MEDLINE COM SRL')]


def test_import_cui_collision_without_resolvable_master_is_skipped(monkeypatch):
    repo = _FakeRepo(raise_on_create=True, cui_hit=None)
    assert _run_import(monkeypatch, Resolution(None, 'none', 'none'), repo) == 'skipped'
    assert repo.aliased == [] and repo.bound == []  # nothing touched on skip


# ── soft-delete / restore Furnizori + audit wiring (routes call the right repo methods,
#    gate on 'edit', map missing→404 and CUI conflict→409). No DB: _repo is monkeypatched,
#    routes are called via .__wrapped__ to bypass @login_required. ──
from flask import Flask as _Flask  # noqa: E402

_test_app = _Flask(__name__)


def _fake_user(uid=7, name='Ana Pop'):
    return type('U', (), {'id': uid, 'name': name, 'is_authenticated': True})()


def test_delete_supplier_denied_without_edit(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda action: False)
    with _test_app.test_request_context():
        _resp, code = r.api_delete_supplier.__wrapped__(5)
    assert code == 403


def test_delete_supplier_soft_deletes_with_actor(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda action: action == 'edit')
    monkeypatch.setattr(r, 'current_user', _fake_user(42, 'Ana'), raising=False)
    seen = {}
    def fake(sid, actor_user_id=None, actor_name=None):
        seen.update(sid=sid, actor_user_id=actor_user_id, actor_name=actor_name); return 1
    monkeypatch.setattr(r._repo, 'soft_delete_supplier', fake)
    with _test_app.test_request_context():
        resp = r.api_delete_supplier.__wrapped__(5)
    assert seen == {'sid': 5, 'actor_user_id': 42, 'actor_name': 'Ana'}
    assert resp.get_json()['success'] is True


def test_delete_supplier_404_when_missing(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', _fake_user(), raising=False)
    monkeypatch.setattr(r._repo, 'soft_delete_supplier', lambda *a, **k: 0)
    with _test_app.test_request_context():
        _resp, code = r.api_delete_supplier.__wrapped__(9)
    assert code == 404


def test_restore_supplier_success(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', _fake_user(1, 'Bob'), raising=False)
    seen = {}
    def fake(sid, actor_user_id=None, actor_name=None):
        seen.update(sid=sid, actor_user_id=actor_user_id, actor_name=actor_name); return 1
    monkeypatch.setattr(r._repo, 'restore_supplier', fake)
    with _test_app.test_request_context():
        resp = r.api_restore_supplier.__wrapped__(5)
    assert seen['sid'] == 5 and seen['actor_name'] == 'Bob'
    assert resp.get_json()['success'] is True


def test_restore_supplier_cui_conflict_returns_409(monkeypatch):
    import core.suppliers.routes as r
    # Under pytest psycopg2 is a MagicMock (see jarvis/conftest.py), so give pg_errors a real
    # exception class for this test; in prod it is the genuine psycopg2 UniqueViolation.
    class _UV(Exception):
        pass
    monkeypatch.setattr(r.pg_errors, 'UniqueViolation', _UV, raising=False)
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', _fake_user(), raising=False)
    def boom(*a, **k):
        raise _UV()
    monkeypatch.setattr(r._repo, 'restore_supplier', boom)
    with _test_app.test_request_context():
        _resp, code = r.api_restore_supplier.__wrapped__(5)
    assert code == 409


def test_delete_preset_passes_actor_for_audit(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', _fake_user(7, 'Bob'), raising=False)
    seen = {}
    def fake(pid, actor_user_id=None, actor_name=None):
        seen.update(pid=pid, actor_user_id=actor_user_id, actor_name=actor_name); return 1
    monkeypatch.setattr(r._repo, 'delete_preset', fake)
    with _test_app.test_request_context():
        r.api_delete_preset.__wrapped__(3, 99)  # (supplier_id, preset_id)
    assert seen == {'pid': 99, 'actor_user_id': 7, 'actor_name': 'Bob'}


def test_list_suppliers_forwards_only_deleted_flag(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    seen = {}
    monkeypatch.setattr(r._repo, 'list_master', lambda **kw: seen.update(kw) or [])
    with _test_app.test_request_context('/api/suppliers?deleted=1'):
        r.api_list_suppliers.__wrapped__()
    assert seen.get('only_deleted') is True
    seen.clear()
    with _test_app.test_request_context('/api/suppliers'):
        r.api_list_suppliers.__wrapped__()
    assert seen.get('only_deleted') is False
