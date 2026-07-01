"""Integration test — Autoworld S1005 reference XML reproduction.

Verifies that build_anaf_xml() reproduces the Autoworld International SRL
balance sheet (12/2025) and validates against the s1005 XSD.

Reference: schemas/Bilant_S1005_AUTOWORLD_complet.xml
"""
from lxml import etree

from accounting.bilant.anaf_exporter import build_anaf_xml
from accounting.bilant.anaf_schemas import get_lxml_schema

# ---------------------------------------------------------------------------
# Reference data from Bilant_S1005_AUTOWORLD_complet.xml
# ---------------------------------------------------------------------------

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

# All 30 F10 tokens — C2 suffix only (new entity, no prior-year column C1)
AUTOWORLD_F10 = {
    'F10_0012': 20550, 'F10_0022': 2369495, 'F10_0042': 2390045,
    'F10_0052': 12329354, 'F10_3012': 21777201, 'F10_0062': 21777201,
    'F10_0082': 2926491, 'F10_0092': 37033046, 'F10_0102': 49470,
    'F10_0112': 49470, 'F10_0132': 26455059, 'F10_0142': 10451119,
    'F10_0152': 12841164, 'F10_0162': 4464641, 'F10_0172': 202890,
    'F10_0182': 176338, 'F10_0192': 118905, 'F10_0202': 118905,
    'F10_0222': 57433, 'F10_0232': 57433, 'F10_0292': 8070,
    'F10_0302': 8070, 'F10_0352': 7158183, 'F10_0362': 657084,
    'F10_0372': 1614, 'F10_0422': 735, 'F10_0432': 351031,
    'F10_0452': 1614, 'F10_0462': 8173633, 'F10_0492': 8173633,
}


def _build_xml() -> bytes:
    """Build XML with the Autoworld reference data."""
    return build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values=AUTOWORLD_F10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_autoworld_xml_validates_against_xsd():
    """Built XML must pass lxml XSD validation for the UU (S1005) schema."""
    xml_bytes = _build_xml()
    schema = get_lxml_schema('UU')
    doc = etree.fromstring(xml_bytes)
    assert schema.validate(doc), '\n'.join(str(e) for e in schema.error_log)


def test_autoworld_xml_contains_expected_f10_tokens():
    """All 30 F10 tokens must be present with their exact integer values."""
    xml_bytes = _build_xml()
    for token, value in AUTOWORLD_F10.items():
        expected_attr = f'{token}="{value}"'.encode()
        assert expected_attr in xml_bytes, (
            f'Expected {token}="{value}" not found in XML output'
        )


def test_autoworld_xml_has_correct_root_element():
    """Root tag must end with Bilant1005 (the S1005 root element name)."""
    xml_bytes = _build_xml()
    doc = etree.fromstring(xml_bytes)
    # lxml tag is '{namespace}Bilant1005'
    assert doc.tag.endswith('Bilant1005'), (
        f'Unexpected root element: {doc.tag!r}'
    )


def test_autoworld_xml_no_spurious_c1_tokens():
    """No C1 tokens should appear — Autoworld is a new entity with no prior year."""
    xml_bytes = _build_xml()
    # C1 tokens end in '1' immediately after the row digits, e.g. F10_0011, F10_0021
    # Our reference data has only C2 tokens (ending in '2'), so no C1 should appear.
    doc = etree.fromstring(xml_bytes)
    f10_el = doc.find('.//{*}F10')
    assert f10_el is not None, 'F10 element missing from output'
    for attr_name in f10_el.attrib:
        assert attr_name.endswith('2') or attr_name == 'F10_3012', (
            f'Unexpected C1 token found: {attr_name}'
        )
