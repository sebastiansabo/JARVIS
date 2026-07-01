"""Tests for ANAF XSD schema loader."""
import os
import pytest

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'schemas')


def test_load_schema_s1005():
    from accounting.bilant.anaf_schemas import load_schema
    path = os.path.join(SCHEMAS_DIR, 's1005_20260312.xsd.xml')
    info = load_schema(path)
    assert info.root_element == 'Bilant1005'
    assert info.namespace == 'mfp:anaf:dgti:s1005:declaratie:v14'
    assert info.tip_bil == 'UU'
    assert 'luna' in info.required_attrs
    assert 'cui' in info.required_attrs
    assert 'den' in info.optional_attrs
    assert 'F10_0012' in info.valid_tokens['F10']
    assert 'F10_0492' in info.valid_tokens['F10']
    assert 'F20_0012' in info.valid_tokens['F20']
    assert 'F40_0011' in info.valid_tokens['F40']


def test_load_schema_s1002():
    from accounting.bilant.anaf_schemas import load_schema
    path = os.path.join(SCHEMAS_DIR, 's1002_20260128.xsd.xml')
    info = load_schema(path)
    assert info.root_element == 'Bilant1002'
    assert info.tip_bil == 'BL'
    assert 'v15' in info.namespace


def test_schemas_registry_loaded():
    from accounting.bilant.anaf_schemas import SCHEMAS
    assert 'UU' in SCHEMAS
    assert 'BL' in SCHEMAS
    assert 'BS' in SCHEMAS
    assert 'SL' in SCHEMAS
    assert SCHEMAS['UU'].root_element == 'Bilant1005'


def test_enum_constraints_extracted():
    from accounting.bilant.anaf_schemas import SCHEMAS
    s = SCHEMAS['UU']
    assert 11 in s.enum_constraints['Int_nomenCalitSType']
    assert 22 in s.enum_constraints['Int_nomenCalitSType']


def test_detect_entity_type_micro():
    from accounting.bilant.anaf_schemas import detect_entity_type
    assert detect_entity_type(active=1_000_000, cifra=2_000_000, salariati=5) == 'UU'


def test_detect_entity_type_large():
    from accounting.bilant.anaf_schemas import detect_entity_type
    assert detect_entity_type(active=30_000_000, cifra=60_000_000, salariati=100) == 'BL'


def test_detect_entity_type_small():
    from accounting.bilant.anaf_schemas import detect_entity_type
    assert detect_entity_type(active=10_000_000, cifra=20_000_000, salariati=30) == 'BS'


def test_pick_schema_path_finds_newest():
    from accounting.bilant.anaf_schemas import pick_schema_path
    path = pick_schema_path('s1005', SCHEMAS_DIR)
    assert path.endswith('s1005_20260312.xsd.xml')
    assert os.path.exists(path)


def test_get_lxml_schema():
    from accounting.bilant.anaf_schemas import get_lxml_schema
    schema = get_lxml_schema('UU')
    assert schema is not None
