# jarvis/tests/carpark/test_shopify_taxonomy_repo.py
from carpark.connectors.shopify.taxonomy_repository import TaxonomyMapRepository

def test_get_map_groups_by_dimension(monkeypatch):
    rows = [
        {'dimension': 'fuel_type', 'source_value': 'Motorină',
         'target_gid': 'gid://.../v1', 'target_label': 'Diesel',
         'shopify_attribute_gid': 'gid://shopify/TaxonomyAttribute/2177'},
        {'dimension': 'color', 'source_value': 'Negru',
         'target_gid': 'gid://.../v2', 'target_label': 'Black',
         'shopify_attribute_gid': 'gid://shopify/TaxonomyAttribute/1'},
    ]
    repo = TaxonomyMapRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: rows)
    m = repo.get_map()
    assert m['fuel_type']['Motorină']['target_label'] == 'Diesel'
    assert repo.resolve(m, 'fuel_type', 'Motorină')['target_gid'] == 'gid://.../v1'
    assert repo.resolve(m, 'fuel_type', 'UNKNOWN') is None

def test_distinct_source_values(monkeypatch):
    repo = TaxonomyMapRepository()
    monkeypatch.setattr(repo, 'query_all',
                        lambda sql, params=None: [{'v': 'Benzină'}, {'v': 'Motorină'}])
    out = repo.distinct_source_values({'fuel_type': 'fuel_type'})
    assert out['fuel_type'] == ['Benzină', 'Motorină']
