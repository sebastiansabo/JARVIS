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


# ─────────────────────────────────────────────────────────────────────────
# Catalog fallback (make/model) — resolve from the synced Autovit vocabulary
# (`carpark_autovit_taxonomy_cache`) when no explicit map row exists, so a
# brand/model that IS a valid Autovit code never needs a per-car manual
# mapping before publish. Scoped to 'make' and 'model' ONLY: enum dimensions
# (fuel/color/body…) keep their curated alias seed — their CarPark values are
# local-language terms that must NOT be guessed against the raw catalog.
#
# Never invents a code: every result is a real catalog code. Matching is
# layered and conservative — an ambiguous collapse (two distinct codes that
# normalize the same) resolves to None (unmapped, blocks) rather than guessing.
import re as _re

_CATALOG_SCOPED = {'make', 'model'}


def _collapse(folded: str) -> str:
    """Separator-insensitive form: drop spaces/hyphens from an already-folded
    value, so `"q3 sportback"` and the catalog code `"q3-sportback"` compare
    equal (`"q3sportback"`)."""
    return _re.sub(r'[\s-]+', '', folded)


def _add(exact: dict, collapsed: dict, key_folded: str, target: dict) -> None:
    """Register one folded key in the exact + collapsed lookup tables, marking
    a collision between two DIFFERENT target codes as ambiguous (None) in BOTH
    tables so it can never silently mis-resolve — a dirty catalog with two
    model codes sharing a label/collapsed form resolves to a block, not a
    coin-flip."""
    if not key_folded:
        return
    for table, tkey in ((exact, key_folded), (collapsed, _collapse(key_folded))):
        prev = table.get(tkey, _MISSING)
        if prev is _MISSING:
            table[tkey] = target
        elif prev is not None and prev['target_code'] != target['target_code']:
            table[tkey] = None  # ambiguous


_MISSING = object()


def build_catalog_index(cache_rows) -> dict:
    """Build the lookup index `resolve_catalog()` consumes from
    `carpark_autovit_taxonomy_cache` rows (`{dimension, code, ro_label,
    make}`). Shape: `{'make': {None: scope}, 'model': {make_code: scope}}`,
    where each `scope` is `{'exact': {folded: target}, 'collapsed':
    {collapsed: target}}`. Both the Autovit `code` and its `ro_label` are
    registered as keys (a CarPark value may equal either)."""
    index: dict = {'make': {None: {'exact': {}, 'collapsed': {}}}, 'model': {}}
    for r in (cache_rows or []):
        dim = r.get('dimension')
        if dim not in _CATALOG_SCOPED:
            continue
        code = r.get('code')
        if not code:
            continue
        target = {'target_code': code, 'target_label': r.get('ro_label')}
        if dim == 'make':
            scope = index['make'][None]
        else:
            mk = fold(r.get('make'))
            scope = index['model'].setdefault(mk, {'exact': {}, 'collapsed': {}})
        _add(scope['exact'], scope['collapsed'], fold(code), target)
        _add(scope['exact'], scope['collapsed'], fold(r.get('ro_label')), target)
    return index


def _match_scope(scope: dict, folded: str):
    """Exact then separator-insensitive lookup of one folded value in a scope.
    Returns the target dict, or None (miss OR ambiguous-collapse)."""
    hit = scope['exact'].get(folded)
    if hit is not None:
        return hit
    return scope['collapsed'].get(_collapse(folded))  # None if absent/ambiguous


def resolve_catalog(index: dict, dimension: str, source_value, make=None):
    """Resolve a CarPark `source_value` to an Autovit catalog target for the
    make/model dimensions, or None. Layered, conservative:

      1. exact fold match on the catalog code or ro_label,
      2. separator-insensitive match (`"Q3 Sportback"` -> `q3-sportback`),
      3. trailing-trim strip — drop the last whitespace/hyphen token and retry
         1-2 until a real code matches or the tokens run out
         (`"Cayenne S"` -> `Cayenne`, `"E-Class"` -> `E`).

    Returns `{'target_code', 'target_label'}` on a hit. None for any
    non-make/model dimension, an absent make-scope, or no confident match."""
    if dimension not in _CATALOG_SCOPED:
        return None
    if dimension == 'make':
        scope = index.get('make', {}).get(None)
    else:
        scope = index.get('model', {}).get(fold(make)) if make is not None else None
    if not scope:
        return None
    f = fold(source_value)
    if not f:
        return None
    hit = _match_scope(scope, f)
    if hit is not None:
        return hit
    # Trim-strip: tokens split on whitespace AND hyphen; retry on each shorter
    # front-prefix. Only for make-scoped models in practice (makes rarely have
    # trailing trim), but harmless for makes.
    tokens = [t for t in _re.split(r'[\s-]+', f) if t]
    for i in range(len(tokens) - 1, 0, -1):
        hit = _match_scope(scope, ' '.join(tokens[:i]))
        if hit is not None:
            return hit
    return None


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
