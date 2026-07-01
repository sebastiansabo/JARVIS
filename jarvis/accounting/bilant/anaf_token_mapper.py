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
