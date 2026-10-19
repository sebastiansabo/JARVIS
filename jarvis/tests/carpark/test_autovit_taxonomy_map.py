"""Tests for the Autovit dimension registry + resolver (Task 2 of the
Autovit Taxonomy Mapping project).

Pure, DB-free: `taxonomy_map.py` does no I/O — it only resolves a CarPark
source value to an Autovit target code via a `mapping` dict shaped like
the DB-backed map (`{dimension: {(source_value, make): {target_code,
target_label}}}`), and emits the resolved code into an advert `params`
dict per the dimension's registered emit-kind (`param` / `flag` / `select`).

See docs/superpowers/specs/2026-10-19-autovit-taxonomy-mapping-design.md
("Resolved after builder-check — Emit semantics per dimension") and
.superpowers/sdd/2026-10-19-autovit-taxonomy-mapping/task-2-brief.md.
"""
from carpark.connectors.autovit import taxonomy_map as tm


def test_resolve_hit():
    mapping = {
        'fuel_type': {
            ('benzina', None): {'target_code': 'petrol', 'target_label': 'Petrol'},
        },
    }
    result = tm.resolve(mapping, 'fuel_type', 'benzina')
    assert result == {'target_code': 'petrol', 'target_label': 'Petrol'}


def test_resolve_miss_returns_none():
    mapping = {
        'fuel_type': {
            ('benzina', None): {'target_code': 'petrol', 'target_label': 'Petrol'},
        },
    }
    # source_value not in the dimension's map
    assert tm.resolve(mapping, 'fuel_type', 'nonexistent') is None
    # dimension not in the mapping at all
    assert tm.resolve(mapping, 'color', 'red') is None


def test_resolve_model_is_make_scoped():
    # Same source_value ("a6") under two different makes must resolve to
    # different Autovit model slugs — model slugs are make-dependent.
    # Map keys are folded (lowercase) — resolve() folds the raw-cased
    # 'Audi'/'Volkswagen' lookup `make` the same way a DB-backed map would
    # already store it (see taxonomy_repository.upsert()).
    mapping = {
        'model': {
            ('a6', 'audi'): {'target_code': 'a6-sportback-e-tron', 'target_label': 'A6 Sportback e-tron'},
            ('a6', 'volkswagen'): {'target_code': 'a6-other', 'target_label': 'A6 (other make)'},
        },
    }
    audi_hit = tm.resolve(mapping, 'model', 'a6', make='Audi')
    vw_hit = tm.resolve(mapping, 'model', 'a6', make='Volkswagen')

    assert audi_hit == {'target_code': 'a6-sportback-e-tron', 'target_label': 'A6 Sportback e-tron'}
    assert vw_hit == {'target_code': 'a6-other', 'target_label': 'A6 (other make)'}
    assert audi_hit != vw_hit

    # Omitting make (or passing a make with no mapped entry) must not fall
    # back to some other make's mapping.
    assert tm.resolve(mapping, 'model', 'a6', make=None) is None


def test_emit_param():
    p = {}
    tm.emit(p, 'fuel_type', 'petrol')
    assert p['fuel_type'] == 'petrol'


def test_emit_flag():
    p = {}
    tm.emit(p, 'equipment', 'apple_carplay')
    assert p['apple_carplay'] == '1'


def test_emit_select():
    p = {}
    tm.emit(p, 'air_conditioning_type', 'automatic')
    assert p['air_conditioning_type'] == 'automatic'


# ── fold() — pure, used by both resolve() (read) and upsert()/seed (write) ──
#
# Controller ruling (correctness fix): resolve() did an EXACT dict lookup
# against a map keyed on folded-lowercase-ASCII seed values, but real
# vehicle data stores mixed-case/diacritic values ("Benzină", "Gri") — a
# guaranteed miss. fold() is the single place both sides of the map now
# agree on.

def test_fold_lowercases_and_strips_diacritics():
    assert tm.fold('Benzină') == 'benzina'


def test_fold_strips_whitespace():
    assert tm.fold('  Gri ') == 'gri'


def test_fold_is_idempotent_on_already_folded_values():
    assert tm.fold('benzina') == 'benzina'


def test_fold_handles_multiple_diacritic_forms():
    # ă/â/î/ș(comma-below)/ş(cedilla)/ț(comma-below)/ţ(cedilla) all fold away.
    assert tm.fold('Scaune încălzite față') == 'scaune incalzite fata'
    assert tm.fold('fața') == 'fata'


def test_resolve_folds_case_and_diacritics():
    mapping = {
        'fuel_type': {
            ('benzina', None): {'target_code': 'petrol', 'target_label': 'Petrol'},
        },
    }
    for raw in ('Benzină', 'BENZINA', ' benzina '):
        assert tm.resolve(mapping, 'fuel_type', raw) == \
            {'target_code': 'petrol', 'target_label': 'Petrol'}


def test_resolve_folds_make_too():
    # Make-scoped (model) lookups must fold `make` the same way as
    # `source_value` — a raw-cased/diacritic make must still hit a
    # folded-key row.
    mapping = {
        'model': {
            ('a6', 'audi'): {'target_code': 'a6-sportback-e-tron', 'target_label': 'A6'},
        },
    }
    assert tm.resolve(mapping, 'model', 'A6', make='AUDI') == \
        {'target_code': 'a6-sportback-e-tron', 'target_label': 'A6'}
