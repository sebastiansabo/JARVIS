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
