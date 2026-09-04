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
