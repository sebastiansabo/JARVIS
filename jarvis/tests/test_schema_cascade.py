from flask import Flask

_test_app = Flask(__name__)


def test_list_allocations_for_cascade_sql_shape(monkeypatch):
    from core.suppliers.repository import SupplierMasterRepository
    repo = SupplierMasterRepository()
    captured = {}
    monkeypatch.setattr(repo, 'query_all', lambda sql, params: captured.update(sql=sql, params=params) or [])
    repo.list_allocations_for_cascade(42)
    assert 'FROM allocations' in captured['sql']
    assert 'line_item_index' in captured['sql']
    assert 'konto_config_id' in captured['sql']
    assert captured['params'] == (42,)


def test_invoice_line_items_parses_json(monkeypatch):
    from core.suppliers.repository import SupplierMasterRepository
    repo = SupplierMasterRepository()
    monkeypatch.setattr(repo, 'query_one', lambda sql, p: {'line_items': '[{"name": "L0", "amount": 10}]'})
    assert repo.invoice_line_items(7) == [{'name': 'L0', 'amount': 10}]
    monkeypatch.setattr(repo, 'query_one', lambda sql, p: {'line_items': None})
    assert repo.invoice_line_items(7) == []


def test_cascade_mode_alloc_when_a_line_has_multiple_zones():
    from core.suppliers.routes import _cascade_mode
    lines = [
        {'index': 0, 'allocations': [{'id': 1}]},
        {'index': 1, 'allocations': [{'id': 2}, {'id': 3}]},
    ]
    assert _cascade_mode(lines) == 'alloc'


def test_cascade_mode_line_when_multiple_lines_single_zone_each():
    from core.suppliers.routes import _cascade_mode
    lines = [
        {'index': 0, 'allocations': [{'id': 1}]},
        {'index': 1, 'allocations': [{'id': 2}]},
    ]
    assert _cascade_mode(lines) == 'line'


def test_cascade_mode_none_for_single_line_single_zone():
    from core.suppliers.routes import _cascade_mode
    assert _cascade_mode([{'index': 0, 'allocations': [{'id': 1}]}]) == 'none'


def test_schema_cascade_route_builds_tree(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r._repo, 'invoice_supplier_name', lambda i: 'ACME SRL')
    monkeypatch.setattr(r._resolver, 'resolve', lambda **k: type('R', (), {'supplier_id': 9})())
    monkeypatch.setattr(r._company_repo, 'query_one', lambda sql, p: {'id': 3})
    monkeypatch.setattr(r._repo, 'list_presets', lambda s, c: [
        {'id': 5, 'name': 'A', 'is_active': True}, {'id': 6, 'name': 'B', 'is_active': False}])
    monkeypatch.setattr(r._repo, 'get_invoice_override_full', lambda i: {'konto_config_id': None, 'per_line': False})
    monkeypatch.setattr(r._repo, 'invoice_line_items', lambda i: [
        {'name': 'L0', 'amount': 100, 'vat_rate': 19}, {'name': 'L1', 'amount': 50, 'vat_rate': 19}])
    monkeypatch.setattr(r._repo, 'list_line_overrides', lambda i: {0: 6})
    monkeypatch.setattr(r._repo, 'list_allocations_for_cascade', lambda i: [
        {'id': 11, 'line_index': 0, 'department': 'X', 'subdepartment': None, 'value': 60, 'konto_config_id': None},
        {'id': 12, 'line_index': 0, 'department': 'Y', 'subdepartment': None, 'value': 40, 'konto_config_id': 5},
        {'id': 13, 'line_index': 1, 'department': 'Z', 'subdepartment': None, 'value': 50, 'konto_config_id': None}])
    with _test_app.test_request_context('/api/suppliers/invoices/42/schema-cascade?company=ACME'):
        resp = r.api_schema_cascade.__wrapped__(42)
    body = resp.get_json()
    assert body['mode'] == 'alloc'         # line 0 has 2 zones
    assert body['active_id'] == 5
    assert len(body['lines']) == 2
    assert body['lines'][0]['line_konto_config_id'] == 6
    assert [a['id'] for a in body['lines'][0]['allocations']] == [11, 12]
    assert body['lines'][1]['allocations'][0]['id'] == 13


def test_schema_cascade_route_requires_company(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    with _test_app.test_request_context('/api/suppliers/invoices/42/schema-cascade'):
        resp, status = r.api_schema_cascade.__wrapped__(42)
    assert status == 400
    assert resp.get_json()['success'] is False


def test_schema_cascade_route_permission_denied(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: False)
    with _test_app.test_request_context('/api/suppliers/invoices/42/schema-cascade?company=ACME'):
        resp, status = r.api_schema_cascade.__wrapped__(42)
    assert status == 403
    assert resp.get_json()['success'] is False


def test_schema_cascade_route_unresolved_supplier_returns_empty(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r._repo, 'invoice_supplier_name', lambda i: None)
    with _test_app.test_request_context('/api/suppliers/invoices/42/schema-cascade?company=ACME'):
        resp = r.api_schema_cascade.__wrapped__(42)
    body = resp.get_json()
    assert body['success'] is True
    assert body['presets'] == []
    assert body['mode'] == 'none'
    assert body['lines'] == []


def _fake_cursor_recorder():
    calls = []
    class Cur:
        def execute(self, sql, params=None):
            calls.append((' '.join(sql.split()), params))
    return Cur(), calls


def test_apply_cascade_alloc_updates_and_clears(monkeypatch):
    from core.suppliers.repository import SupplierMasterRepository
    repo = SupplierMasterRepository()
    cur, calls = _fake_cursor_recorder()
    monkeypatch.setattr(repo, 'execute_many', lambda work: work(cur))
    repo.apply_cascade_alloc(42, {'11': 5, '12': None}, created_by=7)
    joined = ' || '.join(sql for sql, _ in calls)
    assert 'UPDATE allocations SET konto_config_id = %s WHERE id = %s AND invoice_id = %s' in joined
    assert ('UPDATE allocations SET konto_config_id = %s WHERE id = %s AND invoice_id = %s', (5, 11, 42)) in calls
    assert ('UPDATE allocations SET konto_config_id = %s WHERE id = %s AND invoice_id = %s', (None, 12, 42)) in calls
    assert any('DELETE FROM invoice_line_konto_override WHERE invoice_id = %s' in sql for sql, _ in calls)
    assert any('per_line = FALSE' in sql for sql, _ in calls)


def test_apply_cascade_line_upserts_and_clears_allocs(monkeypatch):
    from core.suppliers.repository import SupplierMasterRepository
    repo = SupplierMasterRepository()
    cur, calls = _fake_cursor_recorder()
    monkeypatch.setattr(repo, 'execute_many', lambda work: work(cur))
    repo.apply_cascade_line(42, {'0': 5, '1': None}, created_by=7)
    joined = ' || '.join(sql for sql, _ in calls)
    assert 'per_line' in joined and 'invoice_konto_override' in joined
    assert any('INSERT INTO invoice_line_konto_override' in sql and p == (42, 0, 5, 7) for sql, p in calls)
    assert any('DELETE FROM invoice_line_konto_override WHERE invoice_id = %s AND line_index = %s' in sql
               and p == (42, 1) for sql, p in calls)
    assert any('UPDATE allocations SET konto_config_id = NULL WHERE invoice_id = %s' in sql for sql, _ in calls)


def test_schema_cascade_write_alloc_validates_and_dispatches(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', type('U', (), {'id': 7})(), raising=False)
    monkeypatch.setattr(r, '_preset_owner_error', lambda kc, data: None)  # all valid
    seen = {}
    monkeypatch.setattr(r._repo, 'apply_cascade_alloc', lambda inv, m, created_by=None: seen.update(inv=inv, m=m, by=created_by))
    body = {'mode': 'alloc', 'supplier_id': 9, 'company_id': 3, 'alloc_map': {'11': 5, '12': None}}
    with _test_app.test_request_context(json=body):
        resp = r.api_save_schema_cascade.__wrapped__(42)
    assert resp.get_json() == {'success': True, 'mode': 'alloc'}
    assert seen == {'inv': 42, 'm': {'11': 5, '12': None}, 'by': 7}


def test_schema_cascade_write_rejects_foreign_preset(monkeypatch):
    import core.suppliers.routes as r
    from flask import jsonify
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', type('U', (), {'id': 7})(), raising=False)
    monkeypatch.setattr(r, '_preset_owner_error', lambda kc, data: (jsonify({'success': False}), 400))
    called = {'n': 0}
    monkeypatch.setattr(r._repo, 'apply_cascade_alloc', lambda *a, **k: called.__setitem__('n', called['n'] + 1))
    body = {'mode': 'alloc', 'supplier_id': 9, 'company_id': 3, 'alloc_map': {'11': 999}}
    with _test_app.test_request_context(json=body):
        _resp, code = r.api_save_schema_cascade.__wrapped__(42)
    assert code == 400
    assert called['n'] == 0  # nothing written when a preset is foreign


def test_schema_cascade_write_line_dispatches(monkeypatch):
    import core.suppliers.routes as r
    monkeypatch.setattr(r, '_check_supplier_perm', lambda a: True)
    monkeypatch.setattr(r, 'current_user', type('U', (), {'id': 7})(), raising=False)
    monkeypatch.setattr(r, '_preset_owner_error', lambda kc, data: None)
    seen = {}
    monkeypatch.setattr(r._repo, 'apply_cascade_line', lambda inv, m, created_by=None: seen.update(inv=inv, m=m))
    body = {'mode': 'line', 'supplier_id': 9, 'company_id': 3, 'line_map': {'0': 5, '1': None}}
    with _test_app.test_request_context(json=body):
        resp = r.api_save_schema_cascade.__wrapped__(42)
    assert resp.get_json()['mode'] == 'line'
    assert seen == {'inv': 42, 'm': {'0': 5, '1': None}}


def test_export_precedence_alloc_over_line(monkeypatch):
    """Regression: when an allocation carries a konto (alloc_mode), _build_line_configs iterates
    allocation zones and ignores invoice_line_konto_override — unchanged by this feature."""
    import core.suppliers.routes as r
    monkeypatch.setattr(r._repo, 'list_invoice_allocations_with_konto', lambda i: [
        {'value': 60, 'vat_rate': 0, 'department': 'X', 'konto_config_id': 5, 'line_name': 'L0'},
        {'value': 40, 'vat_rate': 0, 'department': 'Y', 'konto_config_id': None, 'line_name': 'L0'}])
    monkeypatch.setattr(r._repo, 'get_konto_by_id', lambda cid: {'konto': {'id': cid}})
    row = {'id': 42, 'alloc_mode': True, 'per_line': True, 'konto_config_id': 88}
    configs = r._build_line_configs(row, base_konto={'id': 'base'}, company_id=3)
    assert [c['net'] for c in configs] == [60, 40]
    assert configs[0]['config'] == {'id': 5}          # zone konto
    assert configs[1]['config'] == {'id': 88}          # base fallback (base_id), not a line override
