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
