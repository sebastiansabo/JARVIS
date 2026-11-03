"""Catalog fallback: resolve make/model from the synced Autovit vocabulary
(`carpark_autovit_taxonomy_cache`) when no explicit map row exists, so a new
car whose brand/model IS a valid Autovit value never needs a per-car manual
mapping before publish. Autovit is the source of truth for the model taxonomy.

Pure, DB-free: exercises `taxonomy_map.build_catalog_index()` +
`resolve_catalog()` against a tiny catalog mirroring the real shape (Autovit's
model list is finer-grained than CarPark's model field — no plain "A5"
(it's "A5 Coupé"), no "E-Class" (it's "E")).
"""
from carpark.connectors.autovit import taxonomy_map as tm

# A tiny slice shaped exactly like carpark_autovit_taxonomy_cache rows.
CATALOG = [
    {'dimension': 'make', 'code': 'mazda', 'ro_label': 'Mazda', 'make': None},
    {'dimension': 'make', 'code': 'porsche', 'ro_label': 'Porsche', 'make': None},
    {'dimension': 'make', 'code': 'mercedes-benz', 'ro_label': 'Mercedes-Benz', 'make': None},
    {'dimension': 'make', 'code': 'audi', 'ro_label': 'Audi', 'make': None},
    # Porsche models
    {'dimension': 'model', 'code': 'cayenne', 'ro_label': 'Cayenne', 'make': 'porsche'},
    {'dimension': 'model', 'code': 'cayenne-coupe', 'ro_label': 'Cayenne Coupe', 'make': 'porsche'},
    # Audi models (note: base is "A5 Coupé", plus variants)
    {'dimension': 'model', 'code': 'a5', 'ro_label': 'A5 Coupé', 'make': 'audi'},
    {'dimension': 'model', 'code': 'q3', 'ro_label': 'Q3', 'make': 'audi'},
    {'dimension': 'model', 'code': 'q3-sportback', 'ro_label': 'Q3 Sportback', 'make': 'audi'},
    # Mercedes models (note: base is "E", not "E-Class")
    {'dimension': 'model', 'code': 'e', 'ro_label': 'E', 'make': 'mercedes-benz'},
    {'dimension': 'model', 'code': 'e-53-amg', 'ro_label': 'E 53 AMG', 'make': 'mercedes-benz'},
    # enum rows must be ignored by the catalog fallback
    {'dimension': 'fuel_type', 'code': 'petrol', 'ro_label': 'Benzină', 'make': None},
]


def _idx():
    return tm.build_catalog_index(CATALOG)


# ── make: exact + separator/diacritic tolerant ──────────────────────────────

def test_make_exact():
    assert tm.resolve_catalog(_idx(), 'make', 'Mazda')['target_code'] == 'mazda'
    assert tm.resolve_catalog(_idx(), 'make', 'Porsche')['target_code'] == 'porsche'


def test_make_hyphen_and_case():
    # "Mercedes-Benz" matches the code verbatim; "mercedes benz" collapses equal
    assert tm.resolve_catalog(_idx(), 'make', 'Mercedes-Benz')['target_code'] == 'mercedes-benz'
    assert tm.resolve_catalog(_idx(), 'make', 'MERCEDES BENZ')['target_code'] == 'mercedes-benz'


def test_make_miss():
    assert tm.resolve_catalog(_idx(), 'make', 'Lada') is None


# ── model: make-scoped, exact → collapse → trim-strip ───────────────────────

def test_model_exact_code_and_label():
    assert tm.resolve_catalog(_idx(), 'model', 'Cayenne', make='porsche')['target_code'] == 'cayenne'
    assert tm.resolve_catalog(_idx(), 'model', 'A5 Coupé', make='audi')['target_code'] == 'a5'


def test_model_separator_insensitive():
    # "Q3 Sportback" (space) -> catalog code "q3-sportback" (hyphen)
    assert tm.resolve_catalog(_idx(), 'model', 'Q3 Sportback', make='audi')['target_code'] == 'q3-sportback'


def test_model_trim_strip_trailing_token():
    # "Cayenne S" -> strip "S" -> "Cayenne"
    assert tm.resolve_catalog(_idx(), 'model', 'Cayenne S', make='porsche')['target_code'] == 'cayenne'
    # "A5 LIMOUSINE" -> strip -> "A5" -> code a5 (base A5 Coupé)
    assert tm.resolve_catalog(_idx(), 'model', 'A5 LIMOUSINE', make='audi')['target_code'] == 'a5'


def test_model_hyphen_trim_eclass():
    # "E-Class" -> split on hyphen, strip "Class" -> "E" -> code e
    assert tm.resolve_catalog(_idx(), 'model', 'E-Class', make='mercedes-benz')['target_code'] == 'e'


def test_model_prefers_more_specific_variant_over_base():
    # exact/collapse beats trim: "Cayenne Coupe" is its own code, not stripped to cayenne
    assert tm.resolve_catalog(_idx(), 'model', 'Cayenne Coupe', make='porsche')['target_code'] == 'cayenne-coupe'


def test_model_is_make_scoped():
    # Cayenne is a Porsche model, never resolves under Audi
    assert tm.resolve_catalog(_idx(), 'model', 'Cayenne', make='audi') is None
    # model with no make cannot be scoped
    assert tm.resolve_catalog(_idx(), 'model', 'Cayenne', make=None) is None


def test_model_miss_stays_unmapped():
    assert tm.resolve_catalog(_idx(), 'model', 'Totally Unknown', make='porsche') is None


# ── scope guards ────────────────────────────────────────────────────────────

def test_exact_label_collision_is_ambiguous_not_coinflip():
    # Dirty catalog: two DISTINCT codes under one make share a label, and no
    # trim-prefix of the label is itself a clean code. Must resolve to None
    # (block), never silently pick whichever loaded first.
    dirty = [
        {'dimension': 'make', 'code': 'audi', 'ro_label': 'Audi', 'make': None},
        {'dimension': 'model', 'code': 'zeta-one', 'ro_label': 'Zeta Prime', 'make': 'audi'},
        {'dimension': 'model', 'code': 'zeta-two', 'ro_label': 'Zeta Prime', 'make': 'audi'},
    ]
    idx = tm.build_catalog_index(dirty)
    assert tm.resolve_catalog(idx, 'model', 'Zeta Prime', make='audi') is None


def test_enum_dimensions_never_catalog_resolved():
    # fuel_type must NOT be guessed from the catalog even though a row exists
    assert tm.resolve_catalog(_idx(), 'fuel_type', 'Benzină') is None
    assert tm.resolve_catalog(_idx(), 'color', 'Gri') is None


# ── enum keyword fallback (color / body_type / fuel_type) ───────────────────

def test_color_marketing_names():
    # the real exposure: dealer marketing names carry a base colour word
    assert tm.resolve_enum('color', 'Fjord Blue')['target_code'] == 'blue'
    assert tm.resolve_enum('color', 'Nardo Grey')['target_code'] == 'gray'
    assert tm.resolve_enum('color', 'Sophisto Grey')['target_code'] == 'gray'
    assert tm.resolve_enum('color', 'Snow White Pearl')['target_code'] == 'white'
    assert tm.resolve_enum('color', 'British Racing Green')['target_code'] == 'green'


def test_color_romanian_and_slug():
    assert tm.resolve_enum('color', 'Gri')['target_code'] == 'gray'
    assert tm.resolve_enum('color', 'Negru')['target_code'] == 'black'
    assert tm.resolve_enum('color', 'beige')['target_code'] == 'bej'


def test_color_ambiguous_blocks():
    # two distinct base colours -> block, never a coin-flip
    assert tm.resolve_enum('color', 'Blue Grey Metallic') is None
    # no recognised colour word -> block (manual map)
    assert tm.resolve_enum('color', 'Grafit') is None


def test_color_no_substring_false_positive():
    # "redwood" must NOT match "red" (token match, not substring)
    assert tm.resolve_enum('color', 'Redwood') is None


def test_body_synonyms():
    assert tm.resolve_enum('body_type', 'Berlina')['target_code'] == 'sedan'
    assert tm.resolve_enum('body_type', 'Break')['target_code'] == 'combi'
    assert tm.resolve_enum('body_type', 'SUV')['target_code'] == 'suv'
    assert tm.resolve_enum('body_type', 'Off-Road')['target_code'] == 'suv'
    assert tm.resolve_enum('body_type', 'Hatchback')['target_code'] == 'compact'


def test_fuel_specificity_ordered():
    assert tm.resolve_enum('fuel_type', 'Mild Hybrid Diesel')['target_code'] == 'mild-hybrid-diesel'
    assert tm.resolve_enum('fuel_type', 'Mild Hybrid Benzina')['target_code'] == 'mild-hybrid-petrol'
    assert tm.resolve_enum('fuel_type', 'Plug-in Hybrid')['target_code'] == 'plugin-hybrid'
    assert tm.resolve_enum('fuel_type', 'Hybrid')['target_code'] == 'hybrid'
    assert tm.resolve_enum('fuel_type', 'Benzină')['target_code'] == 'petrol'
    assert tm.resolve_enum('fuel_type', 'Motorina')['target_code'] == 'diesel'
    assert tm.resolve_enum('fuel_type', 'Electric')['target_code'] == 'electric'
    # bare "Mild Hybrid" (no petrol/diesel base) must BLOCK, not degrade to full hybrid
    assert tm.resolve_enum('fuel_type', 'Mild Hybrid') is None
    assert tm.resolve_enum('fuel_type', 'MHEV') is None


def test_enum_unknown_and_scope():
    assert tm.resolve_enum('fuel_type', 'Antimatter') is None
    # make/model are NOT enum-resolved here
    assert tm.resolve_enum('make', 'Mazda') is None
    assert tm.resolve_enum('model', 'Cayenne') is None
