"""Tests for the rewritten `vehicle_to_advert` (Task 3 of the Autovit
Taxonomy Mapping project).

DB-free: every test passes a literal `taxonomy_map` shaped like
`AutovitTaxonomyRepository.get_map()`'s output (`{dimension:
{(source_value, make): {target_code, target_label}}}`) — no DB, no
repository involved. `vehicle_to_advert` now resolves EVERY dimension
(make, model, body_type, fuel_type, gearbox, drive, color,
pollution_standard, air_conditioning_type, alloy_wheels_type, equipment)
through this map via `taxonomy_map.resolve()`/`emit()`, and returns
`(advert, unmapped)` — a miss is omitted from `params` (never raw-sent)
and recorded in `unmapped` as `"<dimension>:<source_value>"`.

See `.superpowers/sdd/2026-10-19-autovit-taxonomy-mapping/task-3-brief.md`
and the controller ruling on make-scoped `model` resolution: `make` is
resolved FIRST, and `model` is resolved scoped by that RESOLVED Autovit
make code (not the raw CarPark brand) — if `make` is unmapped, `model` is
unmapped too.
"""
from carpark.connectors.autovit import taxonomy as tx


def _map(**dims):
    """Build a literal taxonomy_map from {dimension: {(source_value, make):
    target_code}} shorthand -> the full {target_code, target_label} shape."""
    out = {}
    for dim, entries in dims.items():
        out[dim] = {key: {'target_code': code, 'target_label': code}
                    for key, code in entries.items()}
    return out


def test_v2a_maps_model_make_scoped():
    # make resolved FIRST ('Audi' -> 'audi'), then model resolved SCOPED by
    # that resolved Autovit make code (not the raw CarPark brand 'Audi').
    # Map keys are folded (resolve() folds the raw-cased lookup the same
    # way a DB-backed map, written through upsert()/the seed, already is).
    tmap = _map(
        make={('audi', None): 'audi'},
        model={('a6 e-tron sportback', 'audi'): 'a6-sportback-e-tron'},
    )
    vehicle = {"brand": "Audi", "model": "A6 e-tron Sportback"}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    assert advert["params"]["make"] == "audi"
    assert advert["params"]["model"] == "a6-sportback-e-tron"
    assert unmapped == []


def test_v2a_equipment_flags():
    tmap = _map(equipment={('carplay', None): 'apple_carplay'})
    vehicle = {"equipment_options": ["carplay"]}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    assert advert["params"]["apple_carplay"] == "1"
    assert unmapped == []


def test_v2a_unmapped_equipment_reported_not_sent():
    tmap = _map(equipment={('carplay', None): 'apple_carplay'})
    vehicle = {"equipment_options": ["carplay", "unknown_slug"]}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    p = advert["params"]
    assert p.get("apple_carplay") == "1"
    assert "unknown_slug" not in p
    assert "equipment:unknown_slug" in unmapped


def test_v2a_unmapped_required_in_list():
    # No map entry at all for body_type -> omitted from params, reported.
    tmap = _map()
    vehicle = {"body_type": "SUV"}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    assert "body_type" not in advert["params"]
    assert "body_type:SUV" in unmapped


def test_v2a_select_dimension():
    tmap = _map(air_conditioning_type={('automatic', None): 'automatic'})
    vehicle = {"air_conditioning_type": "automatic"}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    assert advert["params"]["air_conditioning_type"] == "automatic"
    assert unmapped == []


# ── Extra coverage beyond the brief's 5 named tests ──────────────────────

def test_v2a_make_unmapped_blocks_model_even_if_model_mapped_under_other_make():
    # 'A4' IS mapped, but only under make 'bmw' — with the vehicle's own make
    # ('Audi') unmapped, model must NOT fall back to any other make's entry.
    tmap = _map(model={('a4', 'bmw'): 'a4-under-bmw'})
    vehicle = {"brand": "Audi", "model": "A4"}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    assert "model" not in advert["params"]
    assert "make" not in advert["params"]
    assert "make:Audi" in unmapped
    assert "model:A4" in unmapped


def test_v2a_returns_advert_and_unmapped_as_tuple():
    advert, unmapped = tx.vehicle_to_advert({}, {}, {})
    assert isinstance(advert, dict)
    assert isinstance(unmapped, list)
    assert advert["category_id"] == tx.CARS_CATEGORY_ID


def test_v2a_non_dimension_fields_unchanged():
    # vin/year/mileage/price/booleans/is_imported_car bypass the taxonomy map
    # entirely — unaffected by this rewrite.
    vehicle = {"vin": "TMBJK7NS0K8000001", "year_of_manufacture": 2019,
               "mileage_km": 90000, "current_price": 17000,
               "price_currency": "EUR", "is_registered": True,
               "has_accident_history": False}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, {})
    p = advert["params"]
    assert p["vin"] == "TMBJK7NS0K8000001"
    assert p["year"] == 2019
    assert p["mileage"] == 90000
    assert p["price"] == {"1": 17000, "currency": "EUR"}
    assert p["registered"] == "1"
    assert p["no_accident"] == "1"
    assert p["is_imported_car"] == "0"


def test_v2a_vat_deductible_true_emits_vat_1():
    # Normal regime (vat_deductible=True) -> dealer issues an invoice WITH VAT,
    # so the advert must carry Autovit's vat flag "1" ("factură cu TVA").
    advert, unmapped = tx.vehicle_to_advert({"vat_deductible": True}, {}, {})
    assert advert["params"]["vat"] == "1"


def test_v2a_vat_deductible_false_emits_vat_0():
    # Margin regime (vat_deductible=False) -> no deductible VAT, so the advert
    # must carry vat "0" ("fără TVA"). This is the case Roger reported as
    # wrongly publishing "cu TVA" because the flag was never sent.
    advert, unmapped = tx.vehicle_to_advert({"vat_deductible": False}, {}, {})
    assert advert["params"]["vat"] == "0"


def test_v2a_vat_absent_when_vat_deductible_missing():
    # Unknown regime (vat_deductible absent/None) -> omit vat rather than guess,
    # consistent with every other optional flag's `is not None` guard.
    advert, unmapped = tx.vehicle_to_advert({"brand": "Audi"}, {}, {})
    assert "vat" not in advert["params"]


def test_v2a_equipment_sources_merge_options_and_jsonb_dict():
    # Equipment source values = UNNEST(equipment_options) ∪ truthy keys of
    # the `equipment` JSONB dict (per the design spec) — both land through
    # the SAME 'equipment' dimension resolve.
    tmap = _map(equipment={
        ('carplay', None): 'apple_carplay',
        ('esp', None): 'esp',
        ('abs', None): 'abs',
    })
    vehicle = {"equipment_options": ["carplay"],
               "equipment": {"esp": True, "abs": False}}
    advert, unmapped = tx.vehicle_to_advert(vehicle, {}, tmap)
    p = advert["params"]
    assert p.get("apple_carplay") == "1"
    assert p.get("esp") == "1"
    assert "abs" not in p   # False in the JSONB dict -> not a source value at all
    assert unmapped == []
