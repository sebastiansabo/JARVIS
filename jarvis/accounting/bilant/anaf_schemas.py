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
    required_attrs: dict = field(default_factory=dict)    # {name: type_ref}
    optional_attrs: dict = field(default_factory=dict)    # {name: type_ref}
    valid_tokens: dict = field(default_factory=dict)       # {'F10': set, 'F20': set, ...}
    enum_constraints: dict = field(default_factory=dict)   # {type_name: set of values}
    range_constraints: dict = field(default_factory=dict)  # {type_name: (min, max)}
    pattern_constraints: dict = field(default_factory=dict)  # {type_name: pattern_str}
    f_sections_required: dict = field(default_factory=dict)  # {'F10': True, 'F20': False, ...}


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
            try:
                min_val = float(min_el.get('value'))
                max_val = float(max_el.get('value'))
                # Store as int when possible, float otherwise
                info.range_constraints[name] = (
                    int(min_val) if min_val == int(min_val) else min_val,
                    int(max_val) if max_val == int(max_val) else max_val,
                )
            except (ValueError, TypeError):
                pass
        pat_el = restriction.find(f'{{{XS}}}pattern')
        if pat_el is not None:
            info.pattern_constraints[name] = pat_el.get('value')

    # Parse root complexType for required/optional attrs
    bilant_ct = root.find(f".//{{{XS}}}complexType[@name='{root_type}']")
    if bilant_ct is not None:
        # Structure: complexType > complexContent > restriction
        complex_content = bilant_ct.find(f'{{{XS}}}complexContent')
        if complex_content is not None:
            restriction = complex_content.find(f'{{{XS}}}restriction')
        else:
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
                    required = el.get('minOccurs') != '0'
                    info.f_sections_required[sec_name] = required

    # Parse F-section complexTypes for token names
    for sec in ('F10', 'F20', 'F30', 'F40'):
        ct = root.find(f".//{{{XS}}}complexType[@name='{sec}Type']")
        if ct is None:
            info.valid_tokens[sec] = set()
            continue
        # Structure: complexType > complexContent > restriction  (or direct restriction)
        cc = ct.find(f'{{{XS}}}complexContent')
        if cc is not None:
            r = cc.find(f'{{{XS}}}restriction')
        else:
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
