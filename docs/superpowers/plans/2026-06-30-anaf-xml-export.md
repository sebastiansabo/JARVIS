# ANAF Multi-Schema XML Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the existing JARVIS Bilant module (`jarvis/accounting/bilant/`) to support XSD-driven, multi-schema ANAF XML export for all four annual entity types (S1002/S1003/S1004/S1005), with lxml validation, entity-type detection, and an Identificare sheet contract.

**Architecture:** The existing bilant module already has F10S (49-row balance) and F20 (P&L) computation engines, an ANAF XML exporter (F10-only, S1002/S1003), and a full service layer. We add: (1) an XSD parser that loads schemas at startup, (2) a new generic XML builder that emits F10+F20+F30+F40 child elements and validates against the loaded XSD, (3) an Identificare sheet parser for entity identification, (4) token mappers that convert computed values to ANAF token dicts. The old `generate_anaf_xml()` in `anaf_parser.py` is replaced by the new XSD-validated builder.

**Tech Stack:** Python 3.11, Flask, lxml (new dep), pandas, openpyxl. Existing: PyPDF2, pikepdf, fpdf2.

## Global Constraints

- All XML output MUST validate against the matching XSD via `lxml.etree.XMLSchema` before returning
- Token names come from XSD attribute enumerations — never hardcode token strings
- Sparse C1: only emit F10 C1 tokens the caller explicitly passed; never infer C1 from C2
- Keep existing `process_bilant()`, `/upload`, and filled-PDF flows intact
- Do not touch F30 R19/R20 (headcount), R37 (tichete), or auto-derive F40 movements from balanță
- Follow JARVIS patterns: Blueprint routes, `BilantService` orchestration, `bilant_permission_required` decorator
- All work on `dev` branch

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| CREATE | `jarvis/accounting/bilant/schemas/` | Directory for XSD files |
| COPY | `jarvis/accounting/bilant/schemas/s1002_20260128.xsd.xml` | From `Conta_app/Instructiuni/` |
| COPY | `jarvis/accounting/bilant/schemas/s1003_20260210.xsd.xml` | From `Conta_app/Instructiuni/` |
| COPY | `jarvis/accounting/bilant/schemas/s1004_20260224.xsd.xml` | From `Conta_app/Instructiuni/` |
| COPY | `jarvis/accounting/bilant/schemas/s1005_20260312.xsd.xml` | From `Conta_app/Instructiuni/` |
| COPY | `jarvis/accounting/bilant/schemas/Bilant_S1005_AUTOWORLD_complet.xml` | Reference XML fixture |
| CREATE | `jarvis/accounting/bilant/anaf_schemas.py` | XSD parser, schema registry, entity-type detection |
| CREATE | `jarvis/accounting/bilant/anaf_exporter.py` | XSD-validated XML builder (replaces `generate_anaf_xml` in anaf_parser.py) |
| CREATE | `jarvis/accounting/bilant/anaf_token_mapper.py` | Maps computed F10S/F20 values → ANAF token dicts |
| MODIFY | `jarvis/accounting/bilant/excel_handler.py` | Add `read_identificare_sheet()`, `read_mijloace_fixe_sheet()` |
| MODIFY | `jarvis/accounting/bilant/services/bilant_service.py` | Add `generate_anaf_export_xml()` method |
| MODIFY | `jarvis/accounting/bilant/routes.py` | Update `/download-xml` route to use new exporter |
| MODIFY | `jarvis/accounting/bilant/formula_engine.py` | Entity-type-aware metric row mapping |
| MODIFY | `jarvis/requirements.txt` or top-level | Add `lxml>=5.0.0` |
| CREATE | `jarvis/accounting/bilant/tests/test_anaf_schemas.py` | Schema loader tests |
| CREATE | `jarvis/accounting/bilant/tests/test_anaf_exporter.py` | XML builder + validation tests |
| CREATE | `jarvis/accounting/bilant/tests/test_anaf_token_mapper.py` | Token mapping tests |

---

### Task 1: XSD Schema Loader (`anaf_schemas.py`)

**Files:**
- Copy: `Conta_app/Instructiuni/s100*.xsd.xml` → `jarvis/accounting/bilant/schemas/`
- Copy: `Conta_app/Instructiuni/Bilant_S1005_AUTOWORLD_complet.xml` → `jarvis/accounting/bilant/schemas/`
- Create: `jarvis/accounting/bilant/anaf_schemas.py`
- Create: `jarvis/accounting/bilant/tests/__init__.py`
- Create: `jarvis/accounting/bilant/tests/test_anaf_schemas.py`
- Modify: `jarvis/requirements.txt` — add `lxml>=5.0.0`

**Interfaces:**
- Consumes: XSD files on disk
- Produces:
  - `SCHEMAS: dict[str, SchemaInfo]` — module-level registry keyed by tipBIL (`'UU'`, `'BS'`, `'SL'`, `'BL'`)
  - `SchemaInfo` dataclass with: `xsd_path`, `root_element`, `namespace`, `required_attrs`, `optional_attrs`, `valid_tokens` (dict of `{section: set}`), `enum_constraints` (dict of `{type_name: set|range}`)
  - `load_schema(xsd_path: str) -> SchemaInfo`
  - `detect_entity_type(active: float, cifra: float, salariati: int) -> str`
  - `pick_schema_path(schema_code: str, schemas_dir: str) -> str`
  - `get_lxml_schema(entity_type: str) -> lxml.etree.XMLSchema`

- [ ] **Step 1: Add lxml to requirements**

Add `lxml>=5.0.0` to the project's requirements file. Locate the correct requirements file first:

```bash
# Check which requirements file JARVIS uses
ls jarvis/requirements*.txt
# If not found, check root
ls requirements*.txt
```

Add line: `lxml>=5.0.0`

- [ ] **Step 2: Copy XSD files and reference XML into bilant module**

```bash
mkdir -p jarvis/accounting/bilant/schemas
cp Conta_app/Instructiuni/s1002_20260128.xsd.xml jarvis/accounting/bilant/schemas/
cp Conta_app/Instructiuni/s1003_20260210.xsd.xml jarvis/accounting/bilant/schemas/
cp Conta_app/Instructiuni/s1004_20260224.xsd.xml jarvis/accounting/bilant/schemas/
cp Conta_app/Instructiuni/s1005_20260312.xsd.xml jarvis/accounting/bilant/schemas/
cp Conta_app/Instructiuni/Bilant_S1005_AUTOWORLD_complet.xml jarvis/accounting/bilant/schemas/
```

- [ ] **Step 3: Write failing tests for schema loader**

Create `jarvis/accounting/bilant/tests/__init__.py` (empty) and `jarvis/accounting/bilant/tests/test_anaf_schemas.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_schemas.py -v
```

Expected: All fail with `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 5: Implement `anaf_schemas.py`**

Create `jarvis/accounting/bilant/anaf_schemas.py`:

```python
"""ANAF XSD Schema Loader — parses s100x XSD files at startup.

Builds a registry of schema metadata (root element, namespace, required attrs,
valid tokens, enum constraints) keyed by tipBIL code (UU/BS/SL/BL).

XSD-driven: dropping a new XSD into schemas/ auto-registers it.
"""

import glob
import os
import re
import logging
from dataclasses import dataclass, field

from lxml import etree

logger = logging.getLogger('jarvis.bilant.anaf_schemas')

XS = 'http://www.w3.org/2001/XMLSchema'
_SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), 'schemas')

# tipBIL → schema code prefix mapping
_TIP_BIL_MAP = {'UU': 's1005', 'BS': 's1003', 'SL': 's1004', 'BL': 's1002'}
_CODE_TO_TIP = {v: k for k, v in _TIP_BIL_MAP.items()}


@dataclass
class SchemaInfo:
    xsd_path: str
    root_element: str
    namespace: str
    tip_bil: str
    required_attrs: dict = field(default_factory=dict)   # {name: type_ref}
    optional_attrs: dict = field(default_factory=dict)   # {name: type_ref}
    valid_tokens: dict = field(default_factory=dict)      # {'F10': set, 'F20': set, ...}
    enum_constraints: dict = field(default_factory=dict)  # {type_name: set of values}
    range_constraints: dict = field(default_factory=dict) # {type_name: (min, max)}
    pattern_constraints: dict = field(default_factory=dict) # {type_name: pattern_str}
    f_sections_required: dict = field(default_factory=dict) # {'F10': True, 'F20': False, ...}


def load_schema(xsd_path: str) -> SchemaInfo:
    """Parse a single XSD file and extract all metadata."""
    tree = etree.parse(xsd_path)
    root = tree.getroot()

    namespace = root.get('targetNamespace', '')
    root_el = root.find(f'{{{XS}}}element')
    root_name = root_el.get('name')
    root_type = root_el.get('type')

    # Determine tipBIL from filename pattern s100N
    basename = os.path.basename(xsd_path)
    code_match = re.match(r'(s\d{4})_', basename)
    schema_code = code_match.group(1) if code_match else ''
    tip_bil = _CODE_TO_TIP.get(schema_code, '')

    info = SchemaInfo(
        xsd_path=xsd_path,
        root_element=root_name,
        namespace=namespace,
        tip_bil=tip_bil,
    )

    # Parse simpleType constraints first (needed to resolve attr types)
    for st in root.findall(f'{{{XS}}}simpleType'):
        name = st.get('name')
        restriction = st.find(f'{{{XS}}}restriction')
        if restriction is None:
            continue
        enums = [e.get('value') for e in restriction.findall(f'{{{XS}}}enumeration')]
        if enums:
            # Try to parse as int set; fall back to string set
            try:
                info.enum_constraints[name] = {int(v) for v in enums}
            except (ValueError, TypeError):
                info.enum_constraints[name] = set(enums)
        min_el = restriction.find(f'{{{XS}}}minInclusive')
        max_el = restriction.find(f'{{{XS}}}maxInclusive')
        if min_el is not None and max_el is not None:
            info.range_constraints[name] = (
                int(min_el.get('value')), int(max_el.get('value'))
            )
        pat_el = restriction.find(f'{{{XS}}}pattern')
        if pat_el is not None:
            info.pattern_constraints[name] = pat_el.get('value')

    # Parse root complexType for required/optional attrs
    bilant_ct = root.find(f".//{{{XS}}}complexType[@name='{root_type}']")
    if bilant_ct is not None:
        restriction = bilant_ct.find(f'{{{XS}}}restriction')
        if restriction is not None:
            for attr in restriction.findall(f'{{{XS}}}attribute'):
                attr_name = attr.get('name')
                attr_type = attr.get('type', '')
                if attr.get('use') == 'required':
                    info.required_attrs[attr_name] = attr_type
                else:
                    info.optional_attrs[attr_name] = attr_type

            # Parse F-section child elements (sequence inside restriction)
            seq = restriction.find(f'{{{XS}}}sequence')
            if seq is not None:
                for el in seq.findall(f'{{{XS}}}element'):
                    sec_name = el.get('name')  # F10, F20, F30, F40
                    sec_type = el.get('type')
                    required = el.get('minOccurs') != '0'
                    info.f_sections_required[sec_name] = required

    # Parse F-section complexTypes for token names
    for sec in ('F10', 'F20', 'F30', 'F40'):
        ct = root.find(f".//{{{XS}}}complexType[@name='{sec}Type']")
        if ct is None:
            info.valid_tokens[sec] = set()
            continue
        r = ct.find(f'{{{XS}}}restriction')
        if r is None:
            info.valid_tokens[sec] = set()
            continue
        tokens = set()
        for attr in r.findall(f'{{{XS}}}attribute'):
            tokens.add(attr.get('name'))
        info.valid_tokens[sec] = tokens

    return info


def pick_schema_path(schema_code: str, schemas_dir: str = _SCHEMAS_DIR) -> str:
    """Find the newest XSD for a given schema code (e.g. 's1005').

    Returns the path with the latest date suffix.
    Raises FileNotFoundError if no matching XSD exists.
    """
    pattern = os.path.join(schemas_dir, f'{schema_code}_*.xsd.xml')
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(f'No XSD found for {schema_code} in {schemas_dir}')
    return matches[-1]  # sorted by name → latest date wins


def detect_entity_type(active: float, cifra: float, salariati: int) -> str:
    """Determine entity type from prior-year financials (OMF 2036/2025).

    Thresholds (lei, 2 of 3 criteria):
    - Micro (UU): active ≤2,250,000 AND cifra ≤4,500,000 AND salariati ≤10
    - Small (BS): active ≤25,000,000 AND cifra ≤50,000,000 AND salariati ≤50
    - Large (BL): everything else
    """
    micro_checks = [active <= 2_250_000, cifra <= 4_500_000, salariati <= 10]
    if sum(micro_checks) >= 2:
        return 'UU'
    small_checks = [active <= 25_000_000, cifra <= 50_000_000, salariati <= 50]
    if sum(small_checks) >= 2:
        return 'BS'
    return 'BL'


def get_lxml_schema(entity_type: str) -> etree.XMLSchema:
    """Get a compiled lxml XMLSchema for the given entity type."""
    info = SCHEMAS.get(entity_type)
    if not info:
        raise ValueError(f'Unknown entity type: {entity_type}')
    return etree.XMLSchema(etree.parse(info.xsd_path))


def _load_all_schemas() -> dict:
    """Scan schemas/ directory and load all XSD files."""
    schemas = {}
    for code, tip in _CODE_TO_TIP.items():
        try:
            path = pick_schema_path(code, _SCHEMAS_DIR)
            info = load_schema(path)
            schemas[tip] = info
            logger.info('Loaded ANAF schema %s (%s) from %s', tip, info.root_element, path)
        except FileNotFoundError:
            logger.warning('No XSD found for schema code %s', code)
    return schemas


# Module-level registry — populated at import time
SCHEMAS: dict[str, SchemaInfo] = _load_all_schemas()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_schemas.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add accounting/bilant/schemas/ accounting/bilant/anaf_schemas.py accounting/bilant/tests/
git commit -m "feat(bilant): add XSD-driven schema loader for ANAF multi-schema export"
```

---

### Task 2: XSD-Validated XML Builder (`anaf_exporter.py`)

**Files:**
- Create: `jarvis/accounting/bilant/anaf_exporter.py`
- Create: `jarvis/accounting/bilant/tests/test_anaf_exporter.py`

**Interfaces:**
- Consumes: `anaf_schemas.SCHEMAS`, `anaf_schemas.get_lxml_schema()`, `anaf_schemas.SchemaInfo`
- Produces:
  - `build_anaf_xml(entity_type: str, identification: dict, f10_values: dict, f20_values: dict | None, f30_values: dict | None, f40_values: dict | None) -> bytes`
  - `validate_identification(entity_type: str, identification: dict) -> list[str]` (returns list of error messages, empty if valid)

- [ ] **Step 1: Write failing tests**

Create `jarvis/accounting/bilant/tests/test_anaf_exporter.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_exporter.py -v
```

- [ ] **Step 3: Implement `anaf_exporter.py`**

Create `jarvis/accounting/bilant/anaf_exporter.py`:

```python
"""ANAF XML Exporter — XSD-driven, multi-schema XML builder.

Builds validated ANAF XML for import into the official ANAF forms
(S1002/S1003/S1004/S1005). Validates against the loaded XSD before returning.
"""

import logging
from lxml import etree

from .anaf_schemas import SCHEMAS, get_lxml_schema

logger = logging.getLogger('jarvis.bilant.anaf_exporter')


def validate_identification(entity_type: str, identification: dict) -> list[str]:
    """Validate identification attributes against XSD constraints.

    Returns list of error messages (empty if valid).
    """
    info = SCHEMAS.get(entity_type)
    if not info:
        return [f'Unknown entity type: {entity_type}']

    errors = []

    # Check required attrs are present
    for attr_name, attr_type in info.required_attrs.items():
        if attr_name not in identification:
            errors.append(f'Missing required attribute: {attr_name}')
            continue
        val = str(identification[attr_name])
        # Validate against enum constraints if the type has them
        if attr_type in info.enum_constraints:
            allowed = info.enum_constraints[attr_type]
            # Try int comparison first, fall back to string
            try:
                if int(val) not in allowed:
                    errors.append(
                        f'{attr_name}={val} not in allowed values for {attr_type}: {sorted(allowed)}'
                    )
            except (ValueError, TypeError):
                if val not in allowed:
                    errors.append(
                        f'{attr_name}={val} not in allowed values for {attr_type}: {sorted(allowed)}'
                    )
        # Validate pattern constraints
        if attr_type in info.pattern_constraints:
            import re
            pattern = info.pattern_constraints[attr_type]
            if not re.fullmatch(pattern, val):
                errors.append(f'{attr_name}={val} does not match pattern {pattern}')

    return errors


def build_anaf_xml(
    entity_type: str,
    identification: dict,
    f10_values: dict | None = None,
    f20_values: dict | None = None,
    f30_values: dict | None = None,
    f40_values: dict | None = None,
) -> bytes:
    """Build ANAF XML, validate against XSD, return UTF-8 bytes.

    Args:
        entity_type: 'UU', 'BS', 'SL', or 'BL'
        identification: root element attributes (luna, an, cui, den, ...)
        f10_values: {'F10_0012': int_value, ...} — sparse, only supplied tokens emitted
        f20_values: {'F20_0012': int_value, ...} — optional
        f30_values: {'F30_0012': int_value, ...} — optional
        f40_values: {'F40_0012': int_value, ...} — optional

    Returns:
        UTF-8 encoded XML bytes.

    Raises:
        ValueError: if identification validation fails or XSD validation fails.
    """
    info = SCHEMAS.get(entity_type)
    if not info:
        raise ValueError(f'Unknown entity type: {entity_type}')

    # Validate identification
    id_errors = validate_identification(entity_type, identification)
    if id_errors:
        raise ValueError(f'Identification errors: {"; ".join(id_errors)}')

    # Validate tokens against schema
    for section, values in [('F10', f10_values), ('F20', f20_values),
                             ('F30', f30_values), ('F40', f40_values)]:
        if not values:
            continue
        valid = info.valid_tokens.get(section, set())
        for token in values:
            if token not in valid:
                raise ValueError(f'Token {token} not valid for {section} in {entity_type}')

    # Build XML
    ns = info.namespace
    nsmap = {None: ns, 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
    root = etree.Element(f'{{{ns}}}{info.root_element}', nsmap=nsmap)

    # Set schemaLocation
    schema_basename = __import__('os').path.basename(info.xsd_path)
    root.set(
        f'{{{nsmap["xsi"]}}}schemaLocation',
        f'{ns} {schema_basename}'
    )

    # Set identification attributes (required first, then optional)
    for attr_name in list(info.required_attrs) + list(info.optional_attrs):
        if attr_name in identification:
            root.set(attr_name, str(identification[attr_name]))

    # Add F-section child elements
    for section, values in [('F10', f10_values), ('F20', f20_values),
                             ('F30', f30_values), ('F40', f40_values)]:
        if not values and not info.f_sections_required.get(section, False):
            continue
        child = etree.SubElement(root, f'{{{ns}}}{section}')
        if values:
            # Sort tokens for deterministic output
            for token in sorted(values.keys()):
                val = values[token]
                if val is not None:
                    child.set(token, str(int(round(float(val)))))

    # Serialize
    xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)

    # Validate against XSD
    schema = get_lxml_schema(entity_type)
    doc = etree.fromstring(xml_bytes)
    if not schema.validate(doc):
        error_log = '\n'.join(str(e) for e in schema.error_log)
        raise ValueError(f'XSD validation failed:\n{error_log}')

    logger.info('Built valid ANAF XML for %s (%s), %d F10 + %d F20 + %d F30 + %d F40 tokens',
                entity_type, info.root_element,
                len(f10_values or {}), len(f20_values or {}),
                len(f30_values or {}), len(f40_values or {}))

    return xml_bytes
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_exporter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add accounting/bilant/anaf_exporter.py accounting/bilant/tests/test_anaf_exporter.py
git commit -m "feat(bilant): add XSD-validated multi-schema ANAF XML builder"
```

---

### Task 3: Token Mapper (`anaf_token_mapper.py`)

**Files:**
- Create: `jarvis/accounting/bilant/anaf_token_mapper.py`
- Create: `jarvis/accounting/bilant/tests/test_anaf_token_mapper.py`

**Interfaces:**
- Consumes: `f10s_engine.compute_f10s()` output (`{row_tag: int}`), `f20_engine.compute_f20()` output, `anaf_schemas.SCHEMAS`
- Produces:
  - `map_f10_to_tokens(f10s_values: dict, prior_values: dict | None, entity_type: str) -> dict` — `{'F10_0012': int, ...}`
  - `map_f20_to_tokens(f20_values: dict, entity_type: str) -> dict` — `{'F20_0012': int, ...}`
  - `map_f40_to_tokens(mijloace_fixe: dict, entity_type: str) -> dict` — `{'F40_0012': int, ...}`

- [ ] **Step 1: Write failing tests**

Create `jarvis/accounting/bilant/tests/test_anaf_token_mapper.py`:

```python
"""Tests for ANAF token mapper."""
import pytest


def test_map_f10_c2_basic():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 20550, 'R02': 2369495, 'R04': 2390045, 'R49': 8173633}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert tokens['F10_0012'] == 20550
    assert tokens['F10_0022'] == 2369495
    assert tokens['F10_0042'] == 2390045
    assert tokens['F10_0492'] == 8173633
    # No C1 tokens when prior_values is None
    assert 'F10_0011' not in tokens


def test_map_f10_with_prior():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 20550}
    prior = {'R01': 10000}
    tokens = map_f10_to_tokens(f10s, prior_values=prior, entity_type='UU')
    assert tokens['F10_0012'] == 20550
    assert tokens['F10_0011'] == 10000


def test_map_f10_sub_rows():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R301': 21777201, 'R302': 0}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert tokens['F10_3012'] == 21777201
    assert 'F10_3022' not in tokens  # zero values omitted


def test_map_f10_skips_zero():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    f10s = {'R01': 0, 'R02': 100}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    assert 'F10_0012' not in tokens  # zero omitted
    assert tokens['F10_0022'] == 100


def test_map_f10_validates_tokens():
    from accounting.bilant.anaf_token_mapper import map_f10_to_tokens
    # R99 does not exist in S1005 F10 schema
    f10s = {'R99': 999}
    tokens = map_f10_to_tokens(f10s, prior_values=None, entity_type='UU')
    # Should silently skip invalid tokens (R99 doesn't map to a valid F10 token)
    assert not any('F10_0992' in k for k in tokens)


def test_map_f20_micro():
    from accounting.bilant.anaf_token_mapper import map_f20_to_tokens
    f20 = {'named': {'R01': 242230516, 'R04': 0}, 'standalone': {}, 'rows_with_c1_zero': set()}
    tokens = map_f20_to_tokens(f20, entity_type='UU')
    assert tokens['F20_0012'] == 242230516
    assert 'F20_0042' not in tokens  # zero omitted
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_token_mapper.py -v
```

- [ ] **Step 3: Implement `anaf_token_mapper.py`**

Create `jarvis/accounting/bilant/anaf_token_mapper.py`:

```python
"""ANAF Token Mapper — converts computed F10S/F20 values to ANAF token dicts.

Maps row tags (R01, R301, etc.) to ANAF token names (F10_0012, F20_3022, etc.)
using the valid token set from the loaded XSD schema.
"""

import logging
from .anaf_schemas import SCHEMAS

logger = logging.getLogger('jarvis.bilant.anaf_token_mapper')


def _row_tag_to_token(row_tag: str, col: int, section: str) -> str:
    """Convert row tag + column to ANAF token name.

    R01 + col=2 + F10 → F10_0012
    R301 + col=1 + F10 → F10_3011
    """
    # Strip 'R' prefix
    rd = row_tag.lstrip('R')
    # Pad to 3 digits
    padded = rd.zfill(3)
    return f'{section}_{padded}{col}'


def map_f10_to_tokens(
    f10s_values: dict,
    prior_values: dict | None,
    entity_type: str,
) -> dict:
    """Map F10S computed values to ANAF token dict.

    Args:
        f10s_values: {row_tag: int} from compute_f10s() — C2 (current period)
        prior_values: optional {row_tag: int} for C1 (prior period). Sparse.
        entity_type: 'UU', 'BS', 'SL', 'BL'

    Returns:
        {'F10_0012': int_value, 'F10_3012': int_value, ...} — sparse, zero values omitted.
    """
    info = SCHEMAS.get(entity_type)
    valid = info.valid_tokens.get('F10', set()) if info else set()
    tokens = {}

    # C2 (current period)
    for row_tag, val in (f10s_values or {}).items():
        if val is None or round(float(val)) == 0:
            continue
        token = _row_tag_to_token(row_tag, 2, 'F10')
        if token in valid:
            tokens[token] = int(round(float(val)))

    # C1 (prior period) — sparse, only explicit values
    if prior_values:
        for row_tag, val in prior_values.items():
            token = _row_tag_to_token(row_tag, 1, 'F10')
            if token in valid:
                tokens[token] = int(round(float(val)))

    return tokens


def map_f20_to_tokens(f20_values: dict, entity_type: str) -> dict:
    """Map F20 computed values to ANAF token dict.

    For micro entities (UU), F20 has 9 main rows (R01-R09) + sub-codes (R301-R304).
    For small/large (BS/BL), F20 has 70+ rows.

    The f20_engine outputs:
      {'named': {row_tag: int}, 'standalone': {(row, idx): int}, ...}

    For micro (UU), only rows R01-R09 + R301-R304 map to F20 tokens.
    """
    info = SCHEMAS.get(entity_type)
    valid = info.valid_tokens.get('F20', set()) if info else set()
    tokens = {}

    named = f20_values.get('named', {})
    # Map named rows → F20 tokens (C2 only for current year)
    for row_tag, val in named.items():
        if val is None or round(float(val)) == 0:
            continue
        token = _row_tag_to_token(row_tag, 2, 'F20')
        if token in valid:
            tokens[token] = int(round(float(val)))

    # Standalone sub-rows (e.g. energy breakdown under R18)
    # These map to F20_302x, F20_303x etc. — handled via named rows R302, R303
    # The f20_engine already puts sub-codes in named dict (R306, R307, etc.)
    # For micro entities, only R301-R304 matter

    return tokens


def map_f30_to_tokens(f30_values: dict, entity_type: str) -> dict:
    """Map F30 values to ANAF token dict.

    F30 values must be provided as pre-built token dict
    (F30 computation is too complex to auto-derive from balanță alone).
    This function validates tokens against the schema.
    """
    info = SCHEMAS.get(entity_type)
    valid = info.valid_tokens.get('F30', set()) if info else set()
    tokens = {}
    for token, val in (f30_values or {}).items():
        if val is None:
            continue
        if token in valid:
            tokens[token] = int(round(float(val))) if isinstance(val, (int, float)) else val
    return tokens


def map_f40_to_tokens(f40_values: dict, entity_type: str) -> dict:
    """Map F40 values to ANAF token dict.

    F40 values must be provided as pre-built token dict
    (F40 movements require registrul mijloace fixe, not just balanță).
    This function validates tokens against the schema.
    """
    info = SCHEMAS.get(entity_type)
    valid = info.valid_tokens.get('F40', set()) if info else set()
    tokens = {}
    for token, val in (f40_values or {}).items():
        if val is None:
            continue
        if token in valid:
            tokens[token] = int(round(float(val))) if isinstance(val, (int, float)) else val
    return tokens
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_anaf_token_mapper.py -v
```

- [ ] **Step 5: Commit**

```bash
git add accounting/bilant/anaf_token_mapper.py accounting/bilant/tests/test_anaf_token_mapper.py
git commit -m "feat(bilant): add ANAF token mapper for F10/F20/F30/F40 value conversion"
```

---

### Task 4: Identificare Sheet Parsing + F40 Mijloace Fixe Sheet

**Files:**
- Modify: `jarvis/accounting/bilant/excel_handler.py`
- Create: `jarvis/accounting/bilant/tests/test_excel_identificare.py`

**Interfaces:**
- Consumes: `anaf_schemas.SCHEMAS` for validation
- Produces:
  - `read_identificare_sheet(file_bytes: bytes) -> dict` — returns identification dict
  - `read_mijloace_fixe_sheet(file_bytes: bytes) -> dict | None` — returns F40 token-ready dict or None

- [ ] **Step 1: Write failing tests**

Create `jarvis/accounting/bilant/tests/test_excel_identificare.py`:

```python
"""Tests for Identificare and Mijloace_fixe sheet parsing."""
import io
import pytest
import openpyxl


def _make_xlsx_with_identificare(fields: dict) -> bytes:
    """Helper: create an in-memory xlsx with an Identificare sheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Balanta'
    ws.append(['Cont', 'SFD', 'SFC'])
    ws.append(['101', '100', '0'])

    ws2 = wb.create_sheet('Identificare')
    ws2.append(['Câmp', 'Valoare'])
    for key, val in fields.items():
        ws2.append([key, val])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_identificare_basic():
    from accounting.bilant.excel_handler import read_identificare_sheet
    data = _make_xlsx_with_identificare({
        'CUI': '50186890',
        'Denumire': 'AUTOWORLD INTERNATIONAL SRL',
        'CAEN': '4781',
        'Tip entitate': 'Microentitate',
    })
    result = read_identificare_sheet(data)
    assert result['cui'] == '50186890'
    assert result['den'] == 'AUTOWORLD INTERNATIONAL SRL'
    assert result['caen'] == '4781'
    assert result['entity_type'] == 'UU'


def test_parse_identificare_missing_sheet():
    from accounting.bilant.excel_handler import read_identificare_sheet
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    result = read_identificare_sheet(buf.getvalue())
    assert result is None


def test_parse_mijloace_fixe_present():
    from accounting.bilant.excel_handler import read_mijloace_fixe_sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Mijloace_fixe'
    ws.append(['Cont', 'Sold Inițial', 'Creșteri', 'Reduceri', 'Reduceri dezmembrări'])
    ws.append(['212', 1000, 500, 100, 50])
    buf = io.BytesIO()
    wb.save(buf)
    result = read_mijloace_fixe_sheet(buf.getvalue())
    assert result is not None
    assert '212' in result


def test_parse_mijloace_fixe_absent():
    from accounting.bilant.excel_handler import read_mijloace_fixe_sheet
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    result = read_mijloace_fixe_sheet(buf.getvalue())
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add `read_identificare_sheet()` and `read_mijloace_fixe_sheet()` to `excel_handler.py`**

Append to `jarvis/accounting/bilant/excel_handler.py`:

```python
# Field name mapping: Romanian label → ANAF attribute name
_IDENTIFICARE_MAP = {
    'cui': 'cui', 'cif': 'cui',
    'denumire': 'den',
    'judet': '_judet', 'cod judet': '_cod_judet', 'cod județ (codjj)': 'codJJ',
    'localitate': '_localitate',
    'strada': '_strada', 'numar': '_numar', 'număr': '_numar',
    'telefon': 'telefon',
    'nr. reg. com.': 'regCom', 'nr reg com': 'regCom',
    'caen': 'caen', 'caen efectiv': 'caenE',
    'forma proprietate': 'codPP',
    'an_caen': 'AN_CAEN',
    'an exercitiu': '_an', 'an exercițiu': '_an',
    'luna': '_luna',
    'administrator': 'nume_admin',
    'intocmit': 'nume_intocmit', 'întocmit': 'nume_intocmit',
    'calitate': 'calit_intocmit',
    'cod lei': 'codLEI',
    'bifa aprobare': 'bifa_aprob',
    'tip entitate': '_tip_entitate',
}

_ENTITY_TYPE_MAP = {
    'microentitate': 'UU', 'micro': 'UU', 'uu': 'UU',
    'mica': 'BS', 'mici': 'BS', 'bs': 'BS',
    'mica sl': 'SL', 'sl': 'SL',
    'mare': 'BL', 'mari': 'BL', 'bl': 'BL',
}


def read_identificare_sheet(file_bytes: bytes) -> dict | None:
    """Read the Identificare sheet from an uploaded Excel.

    Returns dict with ANAF attribute names, or None if sheet not found.
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if 'Identificare' not in wb.sheetnames:
        return None

    ws = wb['Identificare']
    raw = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        label = str(row[0]).strip().lower()
        value = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
        mapped = _IDENTIFICARE_MAP.get(label)
        if mapped:
            raw[mapped] = value

    # Build identification dict
    ident = {}
    for key, val in raw.items():
        if not key.startswith('_'):
            ident[key] = val

    # Build adresa from parts
    parts = [raw.get('_judet', ''), raw.get('_localitate', ''),
             raw.get('_strada', ''), raw.get('_numar', '')]
    if any(parts):
        ident['adresa'] = (
            f"Judet: {parts[0]}, Localitate: {parts[1]}, "
            f"Strada: {parts[2]}, Nr.: {parts[3]}, "
        )

    # Set an/luna
    if '_an' in raw:
        ident['an'] = raw['_an']
    if '_luna' in raw:
        ident['luna'] = raw['_luna']

    # Detect entity type
    tip = raw.get('_tip_entitate', '').lower()
    ident['entity_type'] = _ENTITY_TYPE_MAP.get(tip, 'UU')

    # Set fixed fields per entity type
    entity_type = ident['entity_type']
    if entity_type == 'UU':
        ident.setdefault('tipBIL', 'UU')
        ident.setdefault('interes_public', '0')
        ident.setdefault('bifa_art27', '0')
    elif entity_type == 'BS':
        ident.setdefault('tipBIL', 'BS')
        ident.setdefault('interes_public', '0')
        ident.setdefault('bifa_art27', '0')
    elif entity_type == 'SL':
        ident.setdefault('tipBIL', 'SL')
        ident.setdefault('bifa_art27', '1')
        ident.setdefault('bifa_aprob', '0')
    elif entity_type == 'BL':
        ident.setdefault('tipBIL', 'BL')
        ident.setdefault('bifa_art27', '0')

    # Defaults for bifa fields
    for bf in ('bifaMC', 'bifaDD', 'bifaGG', 'bifaAA'):
        ident.setdefault(bf, '0')
    ident.setdefault('totalPlata_A', '0')

    # codTT defaults to codJJ (same county code) if not set
    if 'codJJ' in ident and 'codTT' not in ident:
        ident['codTT'] = ident['codJJ']

    # caenE defaults to caen if not set
    if 'caen' in ident and 'caenE' not in ident:
        ident['caenE'] = ident['caen']

    return ident


def read_mijloace_fixe_sheet(file_bytes: bytes) -> dict | None:
    """Read optional Mijloace_fixe sheet for F40 movements.

    Returns dict: {cont: {'sold_initial': float, 'cresteri': float,
                           'reduceri': float, 'reduceri_dezm': float}}
    or None if sheet not found.
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    if 'Mijloace_fixe' not in wb.sheetnames:
        return None

    ws = wb['Mijloace_fixe']
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        cont = str(row[0]).strip()
        if not cont or not cont[0].isdigit():
            continue
        result[cont] = {
            'sold_initial': float(row[1]) if len(row) > 1 and row[1] else 0,
            'cresteri': float(row[2]) if len(row) > 2 and row[2] else 0,
            'reduceri': float(row[3]) if len(row) > 3 and row[3] else 0,
            'reduceri_dezm': float(row[4]) if len(row) > 4 and row[4] else 0,
        }
    return result if result else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_excel_identificare.py -v
```

- [ ] **Step 5: Commit**

```bash
git add accounting/bilant/excel_handler.py accounting/bilant/tests/test_excel_identificare.py
git commit -m "feat(bilant): add Identificare and Mijloace_fixe sheet parsing"
```

---

### Task 5: Service + Route Wiring

**Files:**
- Modify: `jarvis/accounting/bilant/services/bilant_service.py`
- Modify: `jarvis/accounting/bilant/routes.py`

**Interfaces:**
- Consumes: `anaf_exporter.build_anaf_xml()`, `anaf_token_mapper.*`, `excel_handler.read_identificare_sheet()`, `f10s_engine.compute_f10s()`, `f20_engine.compute_f20()`
- Produces: Updated `/download-xml` route that uses XSD-validated builder

- [ ] **Step 1: Add `generate_anaf_export_xml()` to `BilantService`**

Add this method to `jarvis/accounting/bilant/services/bilant_service.py`:

```python
def generate_anaf_export_xml(self, generation_id, identification_overrides: dict | None = None):
    """Generate XSD-validated ANAF XML for import into official forms.

    Uses the new multi-schema exporter with F10+F20+F30+F40 support.

    Args:
        generation_id: ID of the bilant generation.
        identification_overrides: optional dict to override/supplement identification
            from stored source data. Must include 'entity_type' or 'tipBIL'.
    """
    from ..anaf_exporter import build_anaf_xml
    from ..anaf_token_mapper import map_f10_to_tokens, map_f20_to_tokens
    from ..f10s_engine import compute_f10s

    detail = self.get_generation_detail(generation_id)
    if not detail.success:
        return detail
    generation = detail.data['generation']
    results = detail.data['results']

    try:
        # Determine entity type
        ident = identification_overrides or {}
        entity_type = ident.pop('entity_type', 'UU')

        # Build F10 values from stored accounts or results
        accounts_data = self.generation_repo.get_source_accounts(generation_id)
        f10s_values = {}
        if accounts_data:
            import pandas as pd
            rows = [[c, v.get('sfd', 0) or 0, v.get('sfc', 0) or 0]
                    for c, v in accounts_data.items()]
            if rows:
                df = pd.DataFrame(rows, columns=['Cont', 'SFD', 'SFC'])
                f10s_values = compute_f10s(df)

        if not f10s_values:
            # Fallback: use template-engine results
            for r in results:
                nr = r.get('nr_rd')
                if nr:
                    f10s_values[f'R{nr}' if not nr.startswith('R') else nr] = r.get('value', 0) or 0

        # Map to ANAF tokens
        prior = self._get_prior_results(generation['company_id'], generation_id)
        prior_tagged = {f'R{k}' if not k.startswith('R') else k: v
                       for k, v in (prior or {}).items()}
        f10_tokens = map_f10_to_tokens(f10s_values, prior_tagged, entity_type)

        # F20 tokens (if TSD/TSC data available)
        f20_tokens = None
        if accounts_data:
            from ..f20_engine import compute_f20
            f20_raw = compute_f20(accounts_data)
            f20_tokens = map_f20_to_tokens(f20_raw, entity_type)

        # F30/F40 — pass through from overrides (manual data)
        f30_tokens = ident.pop('f30_values', None)
        f40_tokens = ident.pop('f40_values', None)

        # Set defaults for identification
        ident.setdefault('an', str(generation.get('period_date', '')[:4])
                        if generation.get('period_date') else '2025')
        ident.setdefault('luna', '12')

        xml_bytes = build_anaf_xml(
            entity_type=entity_type,
            identification=ident,
            f10_values=f10_tokens,
            f20_values=f20_tokens,
            f30_values=f30_tokens,
            f40_values=f40_tokens,
        )
        return ServiceResult(success=True, data=xml_bytes)

    except ValueError as e:
        logger.warning('ANAF XML validation failed: %s', e)
        return ServiceResult(success=False, error=str(e), status_code=400)
    except Exception as e:
        logger.exception('ANAF XML export failed: %s', e)
        return ServiceResult(success=False, error=str(e), status_code=500)
```

Add the import at the top of `bilant_service.py`:
```python
# (no new top-level import needed — imports are inside the method to avoid circular deps)
```

- [ ] **Step 2: Update the `/download-xml` route in `routes.py`**

Replace the existing `api_download_generation_xml` route in `jarvis/accounting/bilant/routes.py`:

```python
@bilant_bp.route('/api/generations/<int:generation_id>/download-xml', methods=['GET', 'POST'])
@login_required
@bilant_permission_required('generations', 'export')
def api_download_generation_xml(generation_id):
    """Download bilant as XSD-validated ANAF XML import file.

    GET: Uses default entity type (UU) and minimal identification.
    POST: Accepts JSON body with identification overrides and entity_type.
    """
    identification = {}
    if request.method == 'POST':
        identification = request.get_json(silent=True) or {}

    result = _service.generate_anaf_export_xml(generation_id, identification_overrides=identification)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code

    gen = _generation_repo.get_by_id(generation_id)
    entity_type = identification.get('entity_type', 'UU')
    from .anaf_schemas import _TIP_BIL_MAP
    schema_code = _TIP_BIL_MAP.get(entity_type, 's1005')
    cui = identification.get('cui', '')
    an = identification.get('an', '')
    name = f'Bilant_{schema_code}_{cui}_{an}.xml' if cui else f'Bilant_ANAF_{generation_id}.xml'
    name = name.replace(' ', '_')

    import io as _io
    return send_file(
        _io.BytesIO(result.data),
        mimetype='application/xml',
        as_attachment=True,
        download_name=name,
    )
```

- [ ] **Step 3: Test the wired route manually or with a service-level test**

Verify no import errors:
```bash
cd jarvis && python -c "from accounting.bilant.anaf_exporter import build_anaf_xml; print('OK')"
cd jarvis && python -c "from accounting.bilant.services.bilant_service import BilantService; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add accounting/bilant/services/bilant_service.py accounting/bilant/routes.py
git commit -m "feat(bilant): wire XSD-validated XML export into service and routes"
```

---

### Task 6: Entity-Type-Aware Metrics

**Files:**
- Modify: `jarvis/accounting/bilant/formula_engine.py`
- Modify: `jarvis/migrations/domains/schema_bilant.py` (update seeded metric nr_rd values)

**Interfaces:**
- Consumes: entity_type string
- Produces: `BI_ROW_MAP: dict[str, dict[str, str]]` — per-entity-type row-number mapping for metric configs

- [ ] **Step 1: Add `BI_ROW_MAP` to `formula_engine.py`**

Add near the top of `jarvis/accounting/bilant/formula_engine.py`, after `STANDARD_RATIOS`:

```python
# Row number mapping per entity type for financial metrics.
# Each entity type uses different nr_rd values for the same financial concept.
BI_ROW_MAP = {
    'UU': {  # S1005 micro — 49 rows
        'active_imobilizate': '4',
        'active_circulante': '9',
        'cheltuieli_avans': '10',
        'stocuri': '5',
        'creante': '6',
        'disponibilitati': '8',
        'datorii_termen_scurt': '13',
        'datorii_termen_lung': '16',
        'capitaluri_proprii': '46',
        'capitaluri_total': '49',
        'capital_social': '30',
    },
    'BS': {  # S1003 small — row numbers from full bilant prescurtat
        'active_imobilizate': '25',
        'active_circulante': '42',
        'cheltuieli_avans': '43',
        'stocuri': '30',
        'creante': '36',
        'disponibilitati': '40',
        'datorii_termen_scurt': '54',
        'datorii_termen_lung': '55',
        'capitaluri_proprii': '101',
        'capitaluri_total': '103',
        'capital_social': '81',
    },
    'BL': {  # S1002 large — same as BS for standard OMFP 1802
        'active_imobilizate': '25',
        'active_circulante': '42',
        'cheltuieli_avans': '43',
        'stocuri': '30',
        'creante': '36',
        'disponibilitati': '40',
        'datorii_termen_scurt': '54',
        'datorii_termen_lung': '55',
        'capitaluri_proprii': '101',
        'capitaluri_total': '103',
        'capital_social': '81',
    },
}
# SL uses same rows as BS
BI_ROW_MAP['SL'] = BI_ROW_MAP['BS']
```

- [ ] **Step 2: Update the seeded metric configs in `schema_bilant.py`**

In `jarvis/migrations/domains/schema_bilant.py`, update `_seed_bilant_dynamic_metrics` so that structure metric `nr_rd` values match the `BL`/`BS` defaults (since the default template is the full bilant):

The current values (`25, 30, 36, 40, 100, 53, 64`) should map correctly to the BS/BL row numbers. Verify they do — if not, update. The key correction is:
- `struct_capitaluri_proprii` nr_rd should be `101` (not `100`)
- `struct_datorii_scurt` should be `54` (not `53`)
- `struct_datorii_lung` should be `55` (not `64`)

Update these three rows in the INSERT statement.

- [ ] **Step 3: Commit**

```bash
git add accounting/bilant/formula_engine.py jarvis/migrations/domains/schema_bilant.py
git commit -m "feat(bilant): add entity-type-aware metric row mapping (BI_ROW_MAP)"
```

---

### Task 7: Integration Test with Reference XML

**Files:**
- Create: `jarvis/accounting/bilant/tests/test_integration_autoworld.py`

**Interfaces:**
- Consumes: All previous tasks, reference XML fixture

- [ ] **Step 1: Write integration test**

Create `jarvis/accounting/bilant/tests/test_integration_autoworld.py`:

```python
"""Integration test: build Autoworld S1005 XML and validate against XSD."""
import os
import pytest
from lxml import etree

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), '..', 'schemas')
REFERENCE_XML = os.path.join(SCHEMAS_DIR, 'Bilant_S1005_AUTOWORLD_complet.xml')

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

# F10 tokens from the reference XML (all C2)
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


def test_autoworld_xml_validates_against_xsd():
    """Build XML with Autoworld reference data and validate against S1005 XSD."""
    from accounting.bilant.anaf_exporter import build_anaf_xml
    from accounting.bilant.anaf_schemas import get_lxml_schema

    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values=AUTOWORLD_F10,
    )

    schema = get_lxml_schema('UU')
    doc = etree.fromstring(xml_bytes)
    assert schema.validate(doc), f'XSD validation failed:\n{schema.error_log}'


def test_autoworld_xml_contains_expected_f10_tokens():
    """Verify all expected F10 tokens appear in the generated XML."""
    from accounting.bilant.anaf_exporter import build_anaf_xml

    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values=AUTOWORLD_F10,
    )

    doc = etree.fromstring(xml_bytes)
    ns = 'mfp:anaf:dgti:s1005:declaratie:v14'
    f10 = doc.find(f'{{{ns}}}F10')
    assert f10 is not None

    for token, expected_val in AUTOWORLD_F10.items():
        actual = f10.get(token)
        assert actual is not None, f'Missing token {token}'
        assert int(actual) == expected_val, f'{token}: expected {expected_val}, got {actual}'


def test_autoworld_xml_has_correct_root_element():
    from accounting.bilant.anaf_exporter import build_anaf_xml

    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values=AUTOWORLD_F10,
    )

    doc = etree.fromstring(xml_bytes)
    assert doc.tag.endswith('Bilant1005')


def test_autoworld_xml_no_spurious_c1_tokens():
    """Autoworld is a new entity — no C1 (prior year) tokens should appear."""
    from accounting.bilant.anaf_exporter import build_anaf_xml

    xml_bytes = build_anaf_xml(
        entity_type='UU',
        identification=AUTOWORLD_IDENT,
        f10_values=AUTOWORLD_F10,
    )

    doc = etree.fromstring(xml_bytes)
    ns = 'mfp:anaf:dgti:s1005:declaratie:v14'
    f10 = doc.find(f'{{{ns}}}F10')
    c1_tokens = [k for k in f10.attrib if k.endswith('1') and k.startswith('F10_')]
    assert len(c1_tokens) == 0, f'Unexpected C1 tokens: {c1_tokens}'
```

- [ ] **Step 2: Run integration tests**

```bash
cd jarvis && python -m pytest accounting/bilant/tests/test_integration_autoworld.py -v
```

Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add accounting/bilant/tests/test_integration_autoworld.py
git commit -m "test(bilant): add Autoworld S1005 integration test with XSD validation"
```

---

### Task 8: XSD Diff CLI Tool + Migration Playbook

**Files:**
- Create: `jarvis/accounting/bilant/anaf_schemas_cli.py`

**Interfaces:**
- Consumes: `anaf_schemas.load_schema()`
- Produces: CLI command `python -m accounting.bilant.anaf_schemas_cli diff <old.xsd> <new.xsd>`

- [ ] **Step 1: Create CLI tool**

Create `jarvis/accounting/bilant/anaf_schemas_cli.py`:

```python
"""CLI for ANAF schema management.

Usage:
    python -m accounting.bilant.anaf_schemas_cli diff <old.xsd> <new.xsd>
    python -m accounting.bilant.anaf_schemas_cli list
"""

import sys
from .anaf_schemas import load_schema, SCHEMAS


def cmd_diff(old_path: str, new_path: str):
    """Print differences between two XSD schema files."""
    old = load_schema(old_path)
    new = load_schema(new_path)

    print(f'=== Schema Diff: {old_path} → {new_path} ===\n')

    # Namespace
    if old.namespace != new.namespace:
        print(f'Namespace: {old.namespace} → {new.namespace}')

    # Root element
    if old.root_element != new.root_element:
        print(f'Root element: {old.root_element} → {new.root_element}')

    # Required attrs
    old_req = set(old.required_attrs)
    new_req = set(new.required_attrs)
    added_req = new_req - old_req
    removed_req = old_req - new_req
    if added_req:
        print(f'\nNew required attributes: {sorted(added_req)}')
    if removed_req:
        print(f'\nRemoved required attributes: {sorted(removed_req)}')

    # Optional attrs
    old_opt = set(old.optional_attrs)
    new_opt = set(new.optional_attrs)
    added_opt = new_opt - old_opt
    removed_opt = old_opt - new_opt
    if added_opt:
        print(f'\nNew optional attributes: {sorted(added_opt)}')
    if removed_opt:
        print(f'\nRemoved optional attributes: {sorted(removed_opt)}')

    # Tokens per section
    for sec in ('F10', 'F20', 'F30', 'F40'):
        old_tokens = old.valid_tokens.get(sec, set())
        new_tokens = new.valid_tokens.get(sec, set())
        added = new_tokens - old_tokens
        removed = old_tokens - new_tokens
        if added:
            print(f'\n{sec}: {len(added)} new tokens: {sorted(added)[:10]}{"..." if len(added) > 10 else ""}')
        if removed:
            print(f'\n{sec}: {len(removed)} removed tokens: {sorted(removed)[:10]}{"..." if len(removed) > 10 else ""}')
        if not added and not removed:
            print(f'\n{sec}: no token changes ({len(old_tokens)} tokens)')

    # Enum constraint changes
    old_enums = set(old.enum_constraints)
    new_enums = set(new.enum_constraints)
    for name in sorted(old_enums | new_enums):
        old_vals = old.enum_constraints.get(name, set())
        new_vals = new.enum_constraints.get(name, set())
        if old_vals != new_vals:
            added = new_vals - old_vals
            removed = old_vals - new_vals
            if added or removed:
                print(f'\nEnum {name}: +{len(added)} -{len(removed)}')

    print('\n=== End Diff ===')


def cmd_list():
    """List all loaded schemas."""
    print('Loaded ANAF schemas:\n')
    for tip, info in sorted(SCHEMAS.items()):
        print(f'  {tip}: {info.root_element} ({info.namespace})')
        print(f'    XSD: {info.xsd_path}')
        print(f'    Required attrs: {len(info.required_attrs)}')
        print(f'    F10: {len(info.valid_tokens.get("F10", set()))} tokens')
        print(f'    F20: {len(info.valid_tokens.get("F20", set()))} tokens')
        print(f'    F30: {len(info.valid_tokens.get("F30", set()))} tokens')
        print(f'    F40: {len(info.valid_tokens.get("F40", set()))} tokens')
        print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'diff' and len(sys.argv) == 4:
        cmd_diff(sys.argv[2], sys.argv[3])
    elif cmd == 'list':
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Test the CLI**

```bash
cd jarvis && python -m accounting.bilant.anaf_schemas_cli list
cd jarvis && python -m accounting.bilant.anaf_schemas_cli diff \
    accounting/bilant/schemas/s1005_20260312.xsd.xml \
    accounting/bilant/schemas/s1002_20260128.xsd.xml
```

- [ ] **Step 3: Commit**

```bash
git add accounting/bilant/anaf_schemas_cli.py
git commit -m "feat(bilant): add XSD diff CLI tool for annual schema migration"
```

---

### Task 9: Cleanup — Deprecate Old `generate_anaf_xml` + Frontend Update

**Files:**
- Modify: `jarvis/accounting/bilant/anaf_parser.py` — deprecation note on old `generate_anaf_xml()`
- Modify: `jarvis/accounting/bilant/services/bilant_service.py` — update `generate_anaf_import_xml()` to delegate to new exporter
- Modify: `jarvis/frontend/src/api/bilant.ts` — update download-xml to POST with identification

- [ ] **Step 1: Add deprecation notice to old `generate_anaf_xml`**

In `jarvis/accounting/bilant/anaf_parser.py`, add to the docstring of `generate_anaf_xml()`:

```python
"""Generate ANAF XML import file.

DEPRECATED: Use anaf_exporter.build_anaf_xml() instead.
This function only generates F10 tokens for S1002/S1003.
The new exporter supports all four schemas with F10+F20+F30+F40 and XSD validation.
"""
```

- [ ] **Step 2: Update old `generate_anaf_import_xml` service method**

In `jarvis/accounting/bilant/services/bilant_service.py`, update `generate_anaf_import_xml()` to delegate to the new method:

```python
def generate_anaf_import_xml(self, generation_id):
    """Generate ANAF XML import file.

    Delegates to generate_anaf_export_xml() with default UU entity type.
    """
    return self.generate_anaf_export_xml(generation_id)
```

- [ ] **Step 3: Update frontend API client to support POST with identification**

In `jarvis/frontend/src/api/bilant.ts`, update the `downloadXml` function:

```typescript
downloadXml: async (generationId: number, identification?: Record<string, string>) => {
  const url = `/bilant/api/generations/${generationId}/download-xml`;
  const options: RequestInit = identification
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(identification) }
    : { method: 'GET' };
  const response = await fetch(url, { ...options, credentials: 'include' });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const filename = response.headers.get('content-disposition')?.split('filename=')[1] || `Bilant_ANAF_${generationId}.xml`;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename.replace(/"/g, '');
  a.click();
  URL.revokeObjectURL(a.href);
},
```

- [ ] **Step 4: Commit**

```bash
git add accounting/bilant/anaf_parser.py accounting/bilant/services/bilant_service.py \
    jarvis/frontend/src/api/bilant.ts
git commit -m "refactor(bilant): deprecate old XML exporter, wire new multi-schema exporter"
```

---

## Verification Checklist

After all tasks are complete:

1. **Run all tests:**
   ```bash
   cd jarvis && python -m pytest accounting/bilant/tests/ -v
   ```

2. **Run XSD diff to verify schema awareness:**
   ```bash
   cd jarvis && python -m accounting.bilant.anaf_schemas_cli list
   ```

3. **Manual acceptance test (S1005 / Autoworld):**
   - Upload Autoworld balanță through JARVIS UI
   - Download XML via the updated `/download-xml` endpoint with Autoworld identification
   - Open in official ANAF S1005 form, import, run VALIDARE
   - Must pass with zero "Corelații eronate"

4. **Verify existing flows are intact:**
   - `/upload` (Conta_app style) still works
   - Filled PDF download still works
   - ANAF Excel download still works
   - ANAF TXT download still works
