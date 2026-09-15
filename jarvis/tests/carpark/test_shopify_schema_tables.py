import re
from pathlib import Path

def test_field_and_value_map_tables():
    t = (Path(__file__).resolve().parents[2] / 'migrations/domains/schema_carpark.py').read_text()
    assert 'carpark_shopify_field_map' in t and 'carpark_shopify_value_map' in t
    assert re.search(r'UNIQUE\(\s*target_namespace\s*,\s*target_key\s*\)', t)
    assert re.search(r'UNIQUE\(\s*dimension\s*,\s*source_value\s*\)', t)
    assert 'idx_csfm_active' in t
