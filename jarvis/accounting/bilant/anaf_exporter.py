"""ANAF XML Exporter — XSD-driven, multi-schema XML builder.

Builds validated ANAF XML for import into the official ANAF forms
(S1002/S1003/S1004/S1005). Validates against the loaded XSD before returning.
"""

import logging
import os
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

    # Check required attrs are present and validate their constraints
    for attr_name, attr_type in info.required_attrs.items():
        if attr_name not in identification:
            errors.append(f'Missing required attribute: {attr_name}')
            continue
        val = str(identification[attr_name])

        # Validate against enum constraints
        if attr_type in info.enum_constraints:
            allowed = info.enum_constraints[attr_type]
            # Detect whether enum is int-valued or string-valued
            sample = next(iter(allowed), None)
            if isinstance(sample, int):
                try:
                    int_val = int(val)
                    if int_val not in allowed:
                        errors.append(
                            f'{attr_name}={val} not in allowed values for {attr_type}: {sorted(allowed)}'
                        )
                except (ValueError, TypeError):
                    errors.append(f'{attr_name}={val} is not an integer (expected {attr_type})')
            else:
                # String enum
                if val not in allowed:
                    errors.append(
                        f'{attr_name}={val} not in allowed values for {attr_type}: {sorted(allowed)}'
                    )

        # Validate range constraints (for non-enum integer ranges)
        if attr_type in info.range_constraints and attr_type not in info.enum_constraints:
            min_val, max_val = info.range_constraints[attr_type]
            try:
                num = float(val)
                if not (min_val <= num <= max_val):
                    errors.append(
                        f'{attr_name}={val} out of range [{min_val}, {max_val}] for {attr_type}'
                    )
            except (ValueError, TypeError):
                errors.append(f'{attr_name}={val} is not numeric (expected {attr_type})')

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
        ValueError: if identification validation fails, an unknown token is supplied,
                    or XSD validation fails.
    """
    info = SCHEMAS.get(entity_type)
    if not info:
        raise ValueError(f'Unknown entity type: {entity_type}')

    # Validate identification before building
    id_errors = validate_identification(entity_type, identification)
    if id_errors:
        raise ValueError(f'Identification errors: {"; ".join(id_errors)}')

    # Validate tokens against XSD-known token names
    sections = [('F10', f10_values), ('F20', f20_values), ('F30', f30_values), ('F40', f40_values)]
    for section, values in sections:
        if not values:
            continue
        valid = info.valid_tokens.get(section, set())
        for token in values:
            if token not in valid:
                raise ValueError(f'Token {token} not valid for {section} in {entity_type}')

    # Build XML element tree
    ns = info.namespace
    nsmap = {None: ns, 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
    root = etree.Element(f'{{{ns}}}{info.root_element}', nsmap=nsmap)

    # Set schemaLocation pointing to the XSD filename
    schema_basename = os.path.basename(info.xsd_path)
    root.set(
        '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
        f'{ns} {schema_basename}'
    )

    # Set identification attributes — required first, then optional (preserves declaration order)
    for attr_name in list(info.required_attrs) + list(info.optional_attrs):
        if attr_name in identification:
            root.set(attr_name, str(identification[attr_name]))

    # Add F-section child elements (sparse: only emit sections with values or required ones)
    for section, values in sections:
        is_required = info.f_sections_required.get(section, False)
        if not values and not is_required:
            continue
        child = etree.SubElement(root, f'{{{ns}}}{section}')
        if values:
            # Emit tokens in sorted order for deterministic output
            for token in sorted(values.keys()):
                val = values[token]
                if val is not None:
                    child.set(token, str(int(round(float(val)))))

    # Serialize to bytes
    xml_bytes = etree.tostring(root, xml_declaration=True, encoding='UTF-8', pretty_print=True)

    # XSD validation — raise if invalid
    schema = get_lxml_schema(entity_type)
    doc = etree.fromstring(xml_bytes)
    if not schema.validate(doc):
        error_log = '\n'.join(str(e) for e in schema.error_log)
        raise ValueError(f'XSD validation failed:\n{error_log}')

    logger.info(
        'Built valid ANAF XML for %s (%s): %d F10 + %d F20 + %d F30 + %d F40 tokens',
        entity_type, info.root_element,
        len(f10_values or {}), len(f20_values or {}),
        len(f30_values or {}), len(f40_values or {}),
    )

    return xml_bytes
