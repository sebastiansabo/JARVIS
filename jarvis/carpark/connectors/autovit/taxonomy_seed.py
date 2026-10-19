"""Seed `carpark_autovit_taxonomy_map` from the curated alias tables already
in `taxonomy.py` (Task 4 of the Autovit Taxonomy Mapping project).

Task 3 rewired `vehicle_to_advert` to resolve every enum dimension through
the DB-backed map (`AutovitTaxonomyRepository.get_map()` + `taxonomy_map.
resolve()`) instead of calling `_norm_enum`/`_label_to_slug` directly — but
an EMPTY map means every one of today's working conversions (benzină→petrol,
4x4→all-wheel-permanent, grey→gray, bej→bej, euro aliases, ...) becomes
"unmapped" the moment the publish path stops calling `_norm_enum`. This
module seeds the map, once, straight from the exact alias/slug tables
`_norm_enum` already reads, so the map starts out reproducing today's
behaviour bit-for-bit; an admin can later refine individual rows via the
taxonomy UI without losing this baseline.

`_norm_enum` accepts either an already-canonical slug OR a known RO-label/
variant (folds then checks `slugs` before falling back to `aliases`). To
really not regress, the seed must cover BOTH — not just the alias keys —
otherwise a vehicle whose enum column already stores the Autovit-canonical
slug directly (e.g. `fuel_type = "petrol"`, `color_exterior = "grey"`) would
have no map row and resolve() would report it unmapped, even though
`_norm_enum` always handled it today. `test_seed_color_reverse_quirk`
exercises exactly this for colour (`"grey"`/`"beige"` are slugs, not keys of
`_COLOR_ALIASES`).

Pure function (`build_seed_rows`) + one DB-write helper (`seed_map`) — no
module-level I/O.
"""
from typing import Dict, List, Optional, Tuple

from . import taxonomy as _taxonomy
from .taxonomy_map import fold as _fold

# dimension -> (slugs set, aliases dict), pulled straight from the tables
# `_norm_enum` already reads today. `drive`'s resolved value is written to
# the Autovit `transmission` param (taxonomy_map.DIMENSIONS['drive']), but
# the dimension KEY stored in the map stays 'drive' — emit() already knows
# where to place it; the seed doesn't need to care.
_ENUM_TABLES: Dict[str, Tuple[set, Dict[str, str]]] = {
    'fuel_type': (_taxonomy._FUEL_SLUGS, _taxonomy._FUEL_ALIASES),
    'gearbox': (_taxonomy._GEARBOX_SLUGS, _taxonomy._GEARBOX_ALIASES),
    'drive': (_taxonomy._DRIVE_SLUGS, _taxonomy._DRIVE_ALIASES),
    'body_type': (_taxonomy._BODY_SLUGS, _taxonomy._BODY_ALIASES),
    'pollution_standard': (_taxonomy._EURO_SLUGS, _taxonomy._EURO_ALIASES),
}

_COLOR_DIMENSION = 'color'


def _seed_row(dimension: str, source_value: str, target_code: Optional[str]) -> Optional[dict]:
    """None `target_code` -> no row (mirrors `_norm_enum`'s "omit" default;
    in practice every value visited here comes from a dimension's own
    slugs/aliases table, so a miss can't actually happen — this guard is
    just defensive).

    `source_value` is `fold()`ed — a no-op today since every slug/alias key
    in `taxonomy.py`'s tables is already lowercase ASCII, but it makes the
    seed's keys provably consistent with `taxonomy_map.resolve()`'s folded
    lookup and `AutovitTaxonomyRepository.upsert()`'s folded write, rather
    than relying on the source tables happening to already be folded.
    """
    if not target_code:
        return None
    return {
        'dimension': dimension,
        'source_value': _fold(source_value),
        'make': None,
        'target_code': target_code,
        'target_label': _taxonomy.slug_to_label(target_code),
    }


def build_seed_rows() -> List[dict]:
    """Every row `_norm_enum` (and, for colour, `_REVERSE['color']`) would
    resolve today, for every slug AND alias key of each enum table —
    `{dimension, source_value, make, target_code, target_label}`.

    `make` is always None: none of these six dimensions are make-scoped
    (only `model` is, and `model` has no alias table in `taxonomy.py` to
    seed from — out of scope here).
    """
    rows: Dict[Tuple[str, str, Optional[str]], dict] = {}

    for dimension, (slugs, aliases) in _ENUM_TABLES.items():
        for source_value in set(slugs) | set(aliases.keys()):
            target = _taxonomy._norm_enum(source_value, slugs, aliases)
            row = _seed_row(dimension, source_value, target)
            if row:
                rows[(dimension, source_value, None)] = row

    # Colour is a two-step translation: _norm_enum folds to the carpark
    # CANONICAL colour, then _REVERSE['color'] maps that to the real
    # Autovit wire slug (grey->gray, beige->bej) — exactly what the OLD
    # vehicle_to_advert did before Task 3 removed the call (see taxonomy.py
    # git history, commit 2d5d4e4e2). default="other" mirrors the old
    # free-text degrade; the seed only ever visits known slugs/aliases, so
    # that branch can't actually trigger here.
    color_slugs, color_aliases = _taxonomy._COLOR_SLUGS, _taxonomy._COLOR_ALIASES
    color_reverse = _taxonomy._REVERSE['color']
    for source_value in set(color_slugs) | set(color_aliases.keys()):
        canonical = _taxonomy._norm_enum(source_value, color_slugs, color_aliases, default='other')
        target = color_reverse.get(canonical, canonical)
        row = _seed_row(_COLOR_DIMENSION, source_value, target)
        if row:
            rows[(_COLOR_DIMENSION, source_value, None)] = row

    return list(rows.values())


def seed_map(cursor) -> int:
    """Insert every `build_seed_rows()` row into `carpark_autovit_taxonomy_map`.

    `ON CONFLICT (dimension, source_value, make) DO NOTHING` per the brief —
    note this is only a real idempotency guard for the make-scoped `model`
    dimension (Postgres never treats `NULL = NULL` as a conflict, so a
    second run over a NON-empty table would duplicate every make=NULL row
    here rather than skip it; see `AutovitTaxonomyRepository.upsert`'s own
    NULL-make workaround for the general case). That's fine for THIS
    caller: the schema-init wiring only ever invokes `seed_map` behind an
    "is the table empty" guard, so every row inserted here is genuinely
    new, and `create_schema()` additionally runs under an advisory lock
    serializing concurrent gunicorn workers' boots (see database.py), so
    two processes can't race this into duplicates either.

    Returns the number of rows attempted (not necessarily the number
    actually inserted).
    """
    rows = build_seed_rows()
    for row in rows:
        cursor.execute('''
            INSERT INTO carpark_autovit_taxonomy_map
                (dimension, source_value, make, target_code, target_label)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (dimension, source_value, make) DO NOTHING
        ''', (row['dimension'], row['source_value'], row['make'],
              row['target_code'], row['target_label']))
    return len(rows)
