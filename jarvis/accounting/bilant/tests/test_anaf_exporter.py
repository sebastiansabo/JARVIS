"""Tests for ANAF XML builder with XSD validation."""
import os
import pytest

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'schemas')

# Minimal valid identification for S1005 (UU)
AUTOWORLD_IDENT = {
    'luna': '12', 'an': '2025', 'cui': '50186890',
    'den': 'AUTOWORLD INTERNATIONAL SRL',
    'adresa': 'Judet: Cluj, Localitate: CLUJ-NAPOCA, Strada: CALEA FLORESTI, Nr.: 145, ',
    'regCom': 'J2024002657125',
    'caen': '4781', 'caenE': '4781', 'AN_CAEN': '2025',
    'bifa_aprob': '1', 'bifaMC': '0', 'bifaDD': '0', 'bifaGG': '0', 'bifaAA': '0',
    'bifa_art27': '0', 'tipBIL': 'UU', 'interes_public': '0',
    'codTT': '12', 'codJJ': '12', 'codPP': '35',
    'nume_admin': 'MEZEI LASZLO LEHEL',
    'nume_intocmit': 'BRUSLEA CLAUDIA',
    'calit_intocmit': '13',
    'totalPlata_A': '0',
}


def test_build_minimal_xml_validates_against_xsd():
    from accounting.bilant.anaf_exporter import build_anaf_xml
    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values={'F10_0012': 20550, 'F10_0042': 2390045},
    )
    assert b'Bilant1005' in xml_bytes
    assert b'F10_0012="20550"' in xml_bytes


def test_build_xml_with_f20():
    from accounting.bilant.anaf_exporter import build_anaf_xml
    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values={'F10_0012': 20550},
        f20_values={'F20_0012': 242230516},
    )
    assert b'F20' in xml_bytes
    assert b'F20_0012="242230516"' in xml_bytes


def test_rejects_invalid_token():
    from accounting.bilant.anaf_exporter import build_anaf_xml
    with pytest.raises(ValueError, match='not valid.*F10'):
        build_anaf_xml(
            entity_type='UU',
            identification=AUTOWORLD_IDENT,
            f10_values={'F10_BOGUS': 999},
        )


def test_validate_identification_catches_missing():
    from accounting.bilant.anaf_exporter import validate_identification
    ident = dict(AUTOWORLD_IDENT)
    del ident['cui']
    errors = validate_identification('UU', ident)
    assert any('cui' in e for e in errors)


def test_validate_identification_catches_bad_enum():
    from accounting.bilant.anaf_exporter import validate_identification
    ident = dict(AUTOWORLD_IDENT)
    ident['calit_intocmit'] = '99'
    errors = validate_identification('UU', ident)
    assert any('calit_intocmit' in e for e in errors)


def test_output_validates_against_lxml_xsd():
    from accounting.bilant.anaf_exporter import build_anaf_xml
    from accounting.bilant.anaf_schemas import get_lxml_schema
    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values={'F10_0012': 20550},
    )
    schema = get_lxml_schema('UU')
    doc = __import__('lxml').etree.fromstring(xml_bytes)
    assert schema.validate(doc), schema.error_log


def test_sparse_c1_only_emits_explicit():
    from accounting.bilant.anaf_exporter import build_anaf_xml
    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values={'F10_0012': 20550},  # only C2
    )
    assert b'F10_0011' not in xml_bytes  # C1 not inferred
