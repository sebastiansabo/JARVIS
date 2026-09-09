import re
from pathlib import Path

def test_taxonomy_map_table_defined():
    src = Path(__file__).resolve().parents[2] / 'migrations' / 'domains' / 'schema_carpark.py'
    text = src.read_text()
    assert 'carpark_shopify_taxonomy_map' in text
    assert re.search(r'UNIQUE\s*\(\s*dimension\s*,\s*source_value\s*\)', text)
    assert 'idx_cstm_dimension' in text
