"""Autovit live-taxonomy sync + auto-suggest (Task 5 of the Autovit Taxonomy
Mapping project).

`pull_taxonomy(client)` hits the live Autovit API (category 29's parameter
schema + `/makes` + one `/models/{make}` call per make) and shapes the
result into `carpark_autovit_taxonomy_cache` rows (Task 1's schema: `{
dimension, code, ro_label, param_type, make, options}`), ready to hand to
`AutovitTaxonomyRepository.replace_cache()` (Task 3). It is network I/O —
callers run it from a route/service (an explicit admin "Sync taxonomy"
action), never on the publish hot path (see the design doc's "taxonomy GET
reads the cache" non-goal).

`suggest(cache_rows, dimension, source_value, make=None)` is a PURE function
(no I/O) used by the admin auto-suggest UI: given the synced cache rows for
a dimension, rank candidate Autovit codes against a CarPark source value.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from . import taxonomy_map as _taxonomy_map
from .taxonomy_map import fold as _fold
from .taxonomy import CARS_CATEGORY_ID

# Dimensions resolved from one of category 29's PARAMETERS' `options` dict —
# one cache row per option VALUE. Built straight from the registry
# (taxonomy_map.DIMENSIONS) so this module can't silently drift from it.
# Excludes `make`/`model` (their own dedicated `/makes` and `/models/{make}`
# endpoints, not a category parameter) and `equipment` (one row per
# CHECKBOX PARAM itself — handled separately below, no `options` to expand).
_OPTION_DIMENSIONS: Dict[str, str] = {
    dim: param_name
    for dim, (kind, param_name) in _taxonomy_map.DIMENSIONS.items()
    if kind in ('param', 'select') and dim not in ('make', 'model')
}


def _option_label(value: Any) -> Optional[str]:
    """Option-dict values follow the same `{ro, en}` shape as makes/models
    (`{"audi": {"en": "Audi", "ro": "Audi"}}`); fall back to the raw value
    for anything else (defensive — a plain string is passed through as-is)."""
    if isinstance(value, dict):
        return value.get('ro') or value.get('en')
    return value


def _rows_from_parameters(parameters: List[dict]) -> List[dict]:
    """Category-29 `parameters[]` -> cache rows for every enum/select
    dimension (one row per option value) + equipment (one row per checkbox
    param)."""
    rows: List[dict] = []
    by_code = {p.get('code'): p for p in parameters if isinstance(p, dict)}

    for dimension, param_name in _OPTION_DIMENSIONS.items():
        param = by_code.get(param_name)
        if not param:
            continue
        param_type = param.get('type')
        for code, label in (param.get('options') or {}).items():
            rows.append({
                'dimension': dimension,
                'code': code,
                'ro_label': _option_label(label),
                'param_type': param_type,
                'make': None,
                'options': None,
            })

    for param in parameters:
        if not isinstance(param, dict) or param.get('type') != 'checkbox':
            continue
        rows.append({
            'dimension': 'equipment',
            'code': param.get('code'),
            'ro_label': (param.get('labels') or {}).get('ro'),
            'param_type': 'checkbox',
            'make': None,
            'options': None,
        })

    return rows


def _rows_from_makes(makes: Dict[str, Any]) -> List[dict]:
    return [{
        'dimension': 'make',
        'code': slug,
        'ro_label': _option_label(label),
        'param_type': None,
        'make': None,
        'options': None,
    } for slug, label in (makes or {}).items()]


def _rows_from_models(make_slug: str, models: Dict[str, Any]) -> List[dict]:
    return [{
        'dimension': 'model',
        'code': slug,
        'ro_label': _option_label(label),
        'param_type': None,
        'make': make_slug,
        'options': None,
    } for slug, label in (models or {}).items()]


def pull_taxonomy(client) -> List[dict]:
    """Pull Autovit's live category-29 taxonomy into
    `carpark_autovit_taxonomy_cache` rows (`replace_cache()`'s expected
    shape). One round-trip for the category schema + one for `/makes`, plus
    one `get_models(make)` call PER make — Autovit has no bulk "every model
    of every make" endpoint, so a full sync is O(makes) network calls. This
    is why the design keeps syncing out-of-band (an explicit admin action)
    rather than inline during publish.
    """
    category = client.get_category(CARS_CATEGORY_ID) or {}
    rows = _rows_from_parameters(category.get('parameters') or [])

    makes = client.get_makes() or {}
    rows.extend(_rows_from_makes(makes))
    for make_slug in makes:
        models = client.get_models(make_slug) or {}
        rows.extend(_rows_from_models(make_slug, models))

    return rows


# ── Auto-suggest ────────────────────────────────────────────────────────────
#
# Plain exact-token-set overlap WITHOUT diacritic folding ties (or
# mis-ranks) on Romanian equipment queries: "scaune incalzite fata" (no
# diacritics, as typed by an admin) never exact-matches a cached RO label
# "Scaune încălzite față" token-for-token, so a naive implementation can't
# tell a HEATED-seats code from a VENTILATED one — both only share the
# generic "scaune"/"seats" token. Folding diacritics first (on both the
# query and the labels) makes "incalzite" == "încălzite" so the real
# distinguishing word counts. Code tokens (underscore/hyphen-split) are
# scored too and combined via max(): some queries (e.g. "360" for a
# 360°-view camera) hinge on a token that only shows up in the CODE, not
# necessarily in a (possibly generic) RO label.

_TOKEN_RE = re.compile(r'[a-z0-9]+')

# `_fold` is `taxonomy_map.fold` (imported above) — the SAME canonical
# lower+strip+diacritic-fold `resolve()`/`upsert()` use (NFD-normalize +
# drop combining marks, a superset of the Romanian-only replace table this
# used to carry locally), kept under this module's own name so the
# "fold"/"tokens" vocabulary below reads unchanged.


def _tokens(value: Any) -> set:
    """Diacritic-folded token set; underscores/hyphens split naturally since
    they aren't matched by `[a-z0-9]+`."""
    return set(_TOKEN_RE.findall(_fold(value)))


def _token_set_score(query_tokens: set, candidate_tokens: set) -> float:
    """Overlap coefficient (intersection / smaller set) rather than Jaccard
    (intersection / union): a short, precise label fully contained in a
    longer query shouldn't be penalised for the query's extra words, and a
    completely disjoint pair always scores exactly 0."""
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens)
    if not overlap:
        return 0.0
    return overlap / min(len(query_tokens), len(candidate_tokens))


def suggest(cache_rows: List[dict], dimension: str, source_value: str,
            make: Optional[str] = None, limit: int = 5
            ) -> List[Tuple[str, Optional[str], float]]:
    """Rank `dimension`'s cached Autovit codes against a CarPark
    `source_value`, best match first: `[(code, ro_label, score), ...]`,
    score in (0, 1], truncated to the top `limit`. Zero-scoring rows (no
    token overlap at all) are dropped rather than padding the list.

    `make` scopes the `model` dimension (cache rows carry `make`, same as
    the map/resolver — Task 2/3) to that make's models only; ignored for
    every other dimension.
    """
    query_tokens = _tokens(source_value)
    candidates = [r for r in cache_rows if r.get('dimension') == dimension]
    if dimension == 'model':
        candidates = [r for r in candidates if r.get('make') == make]

    scored: List[Tuple[str, Optional[str], float]] = []
    for row in candidates:
        label_score = _token_set_score(query_tokens, _tokens(row.get('ro_label')))
        code_score = _token_set_score(query_tokens, _tokens(row.get('code')))
        score = max(label_score, code_score)
        if score > 0:
            scored.append((row.get('code'), row.get('ro_label'), round(score, 4)))

    scored.sort(key=lambda t: -t[2])
    return scored[:limit]
