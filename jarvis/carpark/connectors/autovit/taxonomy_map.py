"""Autovit dimension registry + pure resolver (Task 2 of the Autovit Taxonomy
Mapping project).

Pure, standalone, no I/O: no DB, no network, no imports of any other
carpark/shopify module. This is the mechanism — the DB-backed lookup table
(`carpark_autovit_taxonomy_map`, Task 1) is loaded elsewhere (Task 3's
`AutovitTaxonomyRepository.get_map()`) into the `mapping` shape this module
consumes: `{dimension: {(source_value, make): {target_code, target_label}}}`.

Autovit silently drops any advert param value that isn't one of its exact
codes/slugs (see docs/superpowers/specs/2026-10-19-autovit-taxonomy-mapping-design.md).
`resolve()` looks up the DB-confirmed Autovit target for a CarPark value;
`emit()` writes that target into an advert `params` dict at the right place,
per the dimension's registered emit-kind in `DIMENSIONS`.
"""
import unicodedata
from typing import Any, Dict, Optional, Tuple

# Emit kind per dimension — the authority for *where* a resolved target_code
# is written into an advert's `params` dict:
#   ('param', <autovit_param_name>)  -> params[<autovit_param_name>] = target_code
#   ('flag', None)                   -> params[target_code] = '1'  (equipment)
#   ('select', <autovit_param_name>) -> params[<autovit_param_name>] = target_code
#                                        (target_code IS the select's option value)
DIMENSIONS: Dict[str, Tuple[str, Optional[str]]] = {
    'make': ('param', 'make'),
    'model': ('param', 'model'),
    'fuel_type': ('param', 'fuel_type'),
    'gearbox': ('param', 'gearbox'),
    'drive': ('param', 'transmission'),
    'body_type': ('param', 'body_type'),
    'color': ('param', 'color'),
    'pollution_standard': ('param', 'pollution_standard'),
    'air_conditioning_type': ('select', 'air_conditioning_type'),
    'alloy_wheels_type': ('select', 'alloy_wheels_type'),
    'equipment': ('flag', None),
}

# Dimensions whose values, if unmapped, must BLOCK publish (no doomed 400
# round-trip) rather than being omitted+reported like optional equipment.
REQUIRED_DIMENSIONS = {'make', 'model', 'body_type', 'fuel_type', 'color'}


def fold(value: Any) -> str:
    """Canonical fold for taxonomy source values: lowercase, trim leading/
    trailing whitespace, and strip diacritics (NFD-normalize then drop
    combining marks) — e.g. `"Benzină"` -> `"benzina"`, `"  Gri "` ->
    `"gri"`.

    Seed rows (and canonical slugs) are already folded-lowercase ASCII, but
    real vehicle data stores mixed-case/diacritic values — an EXACT dict
    lookup against those seed keys would miss every time. `resolve()`
    (read) and `AutovitTaxonomyRepository.upsert()`/`taxonomy_seed` (write)
    all fold through this one function so the map's keys and every lookup
    against it agree on the same canonical form. Pure, never raises: a
    non-string input is coerced via `str()`.
    """
    text = str(value if value is not None else '').strip().lower()
    text = unicodedata.normalize('NFD', text)
    return ''.join(ch for ch in text if not unicodedata.combining(ch))


def resolve(mapping: dict, dimension: str, source_value: Any,
            make: Optional[str] = None) -> Optional[dict]:
    """Look up the Autovit target for a CarPark `source_value` under
    `dimension` (and, for make-scoped dimensions like `model`, `make`).

    `mapping` is the `{dimension: {(source_value, make): {target_code,
    target_label}}}` shape produced by the DB-backed taxonomy map, keyed on
    `fold()`ed values (see `AutovitTaxonomyRepository.upsert()`). Both
    `source_value` and `make` (when not None) are `fold()`ed here before the
    lookup, so a raw-cased/diacritic CarPark value (e.g. `"Benzină"`) still
    hits a folded-lowercase-ASCII map key (`"benzina"`). Returns the target
    dict (`{target_code, target_label}`) on a hit, or None if the
    dimension, the (source_value, make) key, or the whole mapping is absent.
    Never raises on a miss — callers treat None as "unmapped".
    """
    dim_map = mapping.get(dimension)
    if not dim_map:
        return None
    key = (fold(source_value), fold(make) if make is not None else None)
    return dim_map.get(key)


def emit(params: dict, dimension: str, target_code: str) -> None:
    """Write a resolved `target_code` into `params` at the position
    `DIMENSIONS[dimension]` declares for that dimension.

    - 'param' / 'select': params[<autovit_param_name>] = target_code
    - 'flag': params[target_code] = '1' (target_code IS the equipment code)

    Raises KeyError if `dimension` isn't a registered key of DIMENSIONS —
    callers should only call emit() after a successful resolve() against a
    known dimension.
    """
    kind, param_name = DIMENSIONS[dimension]
    if kind == 'flag':
        params[target_code] = '1'
    else:  # 'param' or 'select'
        params[param_name] = target_code
