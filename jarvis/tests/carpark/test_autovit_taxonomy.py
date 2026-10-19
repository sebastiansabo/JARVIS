from carpark.connectors.autovit import taxonomy as tx
from carpark.connectors.autovit.taxonomy_map import fold

SAMPLE = {
    "title": "Skoda Kodiaq Style", "description": "desc",
    "new_used": "used",
    "params": {
        "vin": "TMBJK7NS0K8000001", "make": "skoda", "model": "kodiaq",
        "year": 2019, "mileage": 90000, "fuel_type": "diesel",
        "gearbox": "automatic", "transmission": "all-wheel-auto",
        "body_type": "suv", "color": "gray", "door_count": "5",
        "engine_capacity": 1968, "engine_power": 190,
        "registered": "1", "no_accident": "1", "service_record": "1",
        "original_owner": "1", "tuning": "0",
        "apple_carplay": "1", "esp": "1",
        "price": {"1": 17124.68, "currency": "EUR", "gross_net": "net"},
    },
}

def test_core_fields_mapped():
    v = tx.advert_to_vehicle(SAMPLE)
    assert v["vin"] == "TMBJK7NS0K8000001"
    assert v["brand"] == "Skoda"          # slug -> label
    assert v["model"] == "Kodiaq"
    assert v["year_of_manufacture"] == 2019
    assert v["mileage_km"] == 90000
    assert v["fuel_type"] == "diesel"
    assert v["transmission"] == "automatic"      # from gearbox
    assert v["drive_type"] == "all-wheel-auto"   # from param 'transmission' (BUG FIX)
    assert v["body_type"] == "suv"
    assert v["color_exterior"] == "grey"         # gray -> grey normalization
    assert v["doors"] == 5
    assert v["engine_displacement_cc"] == 1968
    assert v["engine_power_hp"] == 190
    assert v["current_price"] == 17124.68
    assert v["price_currency"] == "EUR"
    assert v["listing_title"] == "Skoda Kodiaq Style"
    assert v["source"] == "autovit"

def test_boolean_flags_mapped():
    v = tx.advert_to_vehicle(SAMPLE)
    assert v["is_registered"] is True
    assert v["has_accident_history"] is False   # no_accident=1 -> inverse
    assert v["has_service_book"] is True
    assert v["is_first_owner"] is True
    assert v["has_tuning"] is False
    assert v["is_electric_vehicle"] is False    # fuel=diesel

def test_equipment_harvested_into_jsonb():
    v = tx.advert_to_vehicle(SAMPLE)
    assert v["equipment"].get("apple_carplay") is True
    assert v["equipment"].get("esp") is True

def test_all_output_keys_are_updatable():
    from carpark.repositories.vehicle_repository import VEHICLE_UPDATABLE_FIELDS
    v = tx.advert_to_vehicle(SAMPLE)
    assert set(v) <= set(VEHICLE_UPDATABLE_FIELDS)

def test_merge_fields_excludes_internal():
    assert "acquisition_price" not in tx.MERGE_FIELDS
    assert "purchase_price_net" not in tx.MERGE_FIELDS
    assert "brand" in tx.MERGE_FIELDS and "current_price" in tx.MERGE_FIELDS


def _advert(**param_overrides):
    """SAMPLE clone with params overridden (values of None delete the key)."""
    params = dict(SAMPLE["params"])
    for k, val in param_overrides.items():
        if val is None:
            params.pop(k, None)
        else:
            params[k] = val
    return {**SAMPLE, "params": params}


def test_brand_uses_canonical_labels():
    # Acronym / hyphenated makes must map to the app's canonical brand names,
    # not naive title-case (which would give "Bmw", "Mercedes Benz").
    assert tx.advert_to_vehicle(_advert(make="bmw"))["brand"] == "BMW"
    assert tx.advert_to_vehicle(_advert(make="mercedes-benz"))["brand"] == "Mercedes-Benz"
    assert tx.advert_to_vehicle(_advert(make="mg"))["brand"] == "MG"
    assert tx.advert_to_vehicle(_advert(make="mini"))["brand"] == "MINI"
    assert tx.advert_to_vehicle(_advert(make="land-rover"))["brand"] == "Land Rover"


def test_brand_falls_back_to_slug_label_for_unknown_make():
    # A make not in AUTOVIT_BRANDS still gets a reasonable title-cased label.
    assert tx.advert_to_vehicle(_advert(make="acmecars"))["brand"] == "Acmecars"


def test_co2_zero_is_preserved():
    # co2_emissions=0 is real (EVs) and must NOT be dropped by a truthy check.
    v = tx.advert_to_vehicle(_advert(co2_emissions=0))
    assert "co2_emissions" in v
    assert v["co2_emissions"] == 0


def test_co2_missing_is_absent():
    v = tx.advert_to_vehicle(_advert(co2_emissions=None))
    assert "co2_emissions" not in v


def test_vehicle_to_advert_builds_slugs_and_price():
    # Task 3 rewrite: vehicle_to_advert now resolves every dimension through
    # an explicit taxonomy_map (no more in-function alias normalisation) and
    # returns (advert, unmapped) — see test_autovit_vehicle_to_advert.py for
    # the dedicated map-resolution coverage. This test keeps asserting the
    # non-dimension shape (category_id, price, vin, contact...) is unchanged.
    vehicle = {"vin": "TMBJK7NS0K8000001", "brand": "Skoda", "model": "Kodiaq",
               "year_of_manufacture": 2019, "mileage_km": 90000,
               "fuel_type": "diesel", "transmission": "automatic",
               "drive_type": "all-wheel-auto", "body_type": "suv",
               "color_exterior": "grey", "doors": 5, "engine_power_hp": 190,
               "engine_displacement_cc": 1968, "current_price": 17000,
               "price_currency": "EUR", "state": "Rulat",
               "listing_title": "Skoda Kodiaq", "listing_description": "d"}
    account = {"config": {"city_id": 52953, "region_id": 2,
                          "contact_person": "ATW", "phone": "0371521912"}}
    # Map keys are folded (lowercase) — resolve() folds the vehicle's
    # raw-cased brand/model ("Skoda"/"Kodiaq") the same way a DB-backed map
    # (written through upsert()/the seed) already is.
    tmap = {
        'make': {('skoda', None): {'target_code': 'skoda', 'target_label': 'Skoda'}},
        'model': {('kodiaq', 'skoda'): {'target_code': 'kodiaq', 'target_label': 'Kodiaq'}},
        'fuel_type': {('diesel', None): {'target_code': 'diesel', 'target_label': 'Diesel'}},
        'gearbox': {('automatic', None): {'target_code': 'automatic', 'target_label': 'Automatic'}},
        'drive': {('all-wheel-auto', None): {'target_code': 'all-wheel-auto', 'target_label': 'AWD auto'}},
        'body_type': {('suv', None): {'target_code': 'suv', 'target_label': 'SUV'}},
        'color': {('grey', None): {'target_code': 'gray', 'target_label': 'Gray'}},
    }
    ad, unmapped = tx.vehicle_to_advert(vehicle, account, tmap)
    assert unmapped == []
    assert ad["category_id"] == 29
    assert ad["new_used"] == "used"
    p = ad["params"]
    assert p["make"] == "skoda" and p["model"] == "kodiaq"
    assert p["gearbox"] == "automatic"
    assert p["transmission"] == "all-wheel-auto"   # drive back into param name
    assert p["color"] == "gray"   # carpark 'grey' -> Autovit api slug 'gray'
    assert p["price"]["1"] == 17000 and p["price"]["currency"] == "EUR"
    assert p["vin"] == "TMBJK7NS0K8000001"
    # Autovit contact uses `phones` (array), not `phone_numbers`; default business
    assert ad["contact"] == {"person": "ATW", "phones": ["0371521912"]}
    assert ad["advertiser_type"] == "business"
    # create-only required param for cars
    assert p["is_imported_car"] == "0"


_EQUIP_TMAP = {
    'equipment': {
        ('apple_carplay', None): {'target_code': 'apple_carplay', 'target_label': 'CarPlay'},
        ('led_lights', None): {'target_code': 'led_lights', 'target_label': 'LED'},
        ('esp', None): {'target_code': 'esp', 'target_label': 'ESP'},
    },
}


def test_vehicle_to_advert_pushes_equipment_options():
    # Form-entered equipment lives in equipment_options (TEXT[] of Autovit slugs);
    # each must become an Autovit "<slug>"="1" param (resolved through the map's
    # 'equipment' dimension — Task 3 rewrite). Previously only the JSONB
    # `equipment` dict was pushed, so form-entered dotări never reached Autovit.
    ad, unmapped = tx.vehicle_to_advert(
        {"brand": "Audi", "model": "A4", "equipment_options": ["apple_carplay", "led_lights"]},
        {}, _EQUIP_TMAP,
    )
    assert ad["params"].get("apple_carplay") == "1"
    assert ad["params"].get("led_lights") == "1"


def test_vehicle_to_advert_merges_equipment_dict_and_options():
    ad, unmapped = tx.vehicle_to_advert(
        {"brand": "Audi", "model": "A4",
         "equipment": {"esp": True, "abs": False},
         "equipment_options": ["apple_carplay"]},
        {}, _EQUIP_TMAP,
    )
    p = ad["params"]
    assert p.get("esp") == "1"            # JSONB True flag still pushed
    assert "abs" not in p                 # JSONB False flag not pushed
    assert p.get("apple_carplay") == "1"  # options slug pushed


def test_vehicle_to_advert_enriches_optional_params():
    # Params Autovit also supports (it SENDS them on pull) that push previously
    # dropped — now emitted so published adverts are fuller. Needs a live
    # create-advert smoke test (dry_run/draft) before prod; staging-only until then.
    v = {"brand": "Audi", "model": "A4",
         "seats": 5, "co2_emissions": 120, "generation": "B9", "variant": "2.0 TDI",
         "is_registered": True, "is_first_owner": True, "has_service_book": True,
         "has_tuning": False, "is_vintage": False, "has_accident_history": False}
    p = tx.vehicle_to_advert(v, {}, {})[0]["params"]
    assert p["nr_seats"] == 5
    assert p["co2_emissions"] == 120
    assert p["generation"] == "B9"
    assert p["version"] == "2.0 TDI"
    assert p["registered"] == "1"
    assert p["original_owner"] == "1"
    assert p["service_record"] == "1"
    assert p["tuning"] == "0"
    assert p["historical_vehicle"] == "0"
    assert p["no_accident"] == "1"  # not has_accident_history -> no_accident=1


def test_vehicle_to_advert_omits_absent_optional_params():
    # A sparse vehicle must not force empty/None optional params onto the advert.
    p = tx.vehicle_to_advert({"brand": "Audi", "model": "A4"}, {}, {})[0]["params"]
    for k in ("nr_seats", "co2_emissions", "generation", "version",
              "registered", "original_owner", "service_record", "tuning",
              "historical_vehicle", "no_accident"):
        assert k not in p


def test_vehicle_to_advert_color_reverse_map():
    # PUSH: carpark canonical color -> live Autovit api slug, resolved through
    # an explicit map entry (Task 3 rewrite — no more built-in _REVERSE
    # lookup inside vehicle_to_advert). Only grey/beige differ from identity
    # (grey->gray, beige->bej); everything else is 1:1 — this asserts the
    # map-driven wiring reproduces the same real-slug values either way.
    def _color(c, target):
        tmap = {'color': {(c, None): {'target_code': target, 'target_label': target}}}
        return tx.vehicle_to_advert({"color_exterior": c}, {}, tmap)[0]["params"]["color"]
    assert _color("grey", "gray") == "gray"
    assert _color("beige", "bej") == "bej"
    assert _color("black", "black") == "black"
    assert _color("red", "red") == "red"


def test_advert_to_vehicle_color_pull_map():
    # PULL: live Autovit api slug -> carpark canonical color (inverse of push).
    assert tx.advert_to_vehicle(_advert(color="gray"))["color_exterior"] == "grey"
    assert tx.advert_to_vehicle(_advert(color="bej"))["color_exterior"] == "beige"
    assert tx.advert_to_vehicle(_advert(color="black"))["color_exterior"] == "black"


def test_advert_to_vehicle_pulls_euro_country_vintage():
    # These Autovit params have JARVIS columns but were previously discarded on
    # import (advert_to_vehicle never read them).
    v = tx.advert_to_vehicle({"params": {
        "make": "bmw", "model": "x3",
        "pollution_standard": "Euro 6", "country_origin": "Germania",
        "historical_vehicle": "1",
    }})
    assert v["euro_standard"] == "Euro 6"
    assert v["country_of_origin"] == "Germania"
    assert v["is_vintage"] is True


def test_push_normalizes_romanian_and_variant_enum_values():
    # carpark_vehicles stores a MIX of Autovit slugs, Romanian labels and short
    # forms (manual entry / legacy import — see the 2026-10-15 data audit).
    # Task 3 rewrite: vehicle_to_advert no longer normalises these itself —
    # it resolves each RAW source value through an explicit taxonomy_map
    # entry (seeded from exactly this kind of alias by Task 4). This test
    # keeps asserting the dimension-to-param WIRING (gearbox, drive->
    # "transmission" param, body_type, color, fuel_type) is correct end to end.
    v = {"brand": "Audi", "model": "A4",
         "fuel_type": "Diesel", "transmission": "Automat",
         "drive_type": "fwd", "body_type": "SUV", "color_exterior": "Negru"}
    # Map keys are folded (lowercase) — resolve() folds the raw-cased
    # lookup values ("Diesel"/"Automat"/"SUV"/"Negru") the same way a
    # DB-backed map already is.
    tmap = {
        'fuel_type': {('diesel', None): {'target_code': 'diesel', 'target_label': 'Diesel'}},
        'gearbox': {('automat', None): {'target_code': 'automatic', 'target_label': 'Automat'}},
        'drive': {('fwd', None): {'target_code': 'front-wheel', 'target_label': 'FWD'}},
        'body_type': {('suv', None): {'target_code': 'suv', 'target_label': 'SUV'}},
        'color': {('negru', None): {'target_code': 'black', 'target_label': 'Black'}},
    }
    p = tx.vehicle_to_advert(v, {}, tmap)[0]["params"]
    assert p["fuel_type"] == "diesel"
    assert p["gearbox"] == "automatic"
    assert p["transmission"] == "front-wheel"   # Autovit param "transmission" = drive
    assert p["body_type"] == "suv"
    assert p["color"] == "black"


def test_push_normalizes_diacritic_labels():
    v = {"brand": "Audi", "model": "A4",
         "fuel_type": "Benzină", "transmission": "Manuală",
         "drive_type": "awd", "color_exterior": "Gri"}
    # Map keys are folded (lowercase + diacritics stripped) — resolve()
    # folds the raw diacritic lookup values the same way.
    tmap = {
        'fuel_type': {('benzina', None): {'target_code': 'petrol', 'target_label': 'Petrol'}},
        'gearbox': {('manuala', None): {'target_code': 'manual', 'target_label': 'Manual'}},
        'drive': {('awd', None): {'target_code': 'all-wheel-permanent', 'target_label': 'AWD'}},
        'color': {('gri', None): {'target_code': 'gray', 'target_label': 'Gray'}},
    }
    p = tx.vehicle_to_advert(v, {}, tmap)[0]["params"]
    assert p["fuel_type"] == "petrol"
    assert p["gearbox"] == "manual"
    assert p["transmission"] == "all-wheel-permanent"
    assert p["color"] == "gray"   # 'Gri' maps directly to the Autovit api slug 'gray'


def test_push_normalizes_gearbox_variants():
    for stored in ("dual-clutch", "cvt", "Automată"):
        # Map key is folded — resolve() folds `stored` the same way a
        # DB-backed map already is (a no-op for the already-lowercase-ASCII
        # variants, but required for "Automată"'s diacritic).
        tmap = {'gearbox': {(fold(stored), None): {'target_code': 'automatic', 'target_label': 'Automatic'}}}
        p = tx.vehicle_to_advert({"brand": "Audi", "model": "A4",
                                  "transmission": stored}, {}, tmap)[0]["params"]
        assert p["gearbox"] == "automatic", stored


def test_push_drops_unmappable_enum_rather_than_sending_raw():
    # A value with no map entry must be omitted (Autovit drops it anyway, and
    # a bad REQUIRED param could 400 the whole create) and reported in
    # `unmapped` — never raw-sent. Task 3 rewrite: an unmapped miss is no
    # longer degraded to a default (the old 'other' color fallback lived in
    # the removed _norm_enum call); Task 6's publish route is where a
    # REQUIRED-dimension miss like this blocks the publish pre-flight.
    v = {"brand": "Audi", "model": "A4",
         "transmission": "spaceship", "color_exterior": "Fjord Blue"}
    advert, unmapped = tx.vehicle_to_advert(v, {}, {})
    p = advert["params"]
    assert "gearbox" not in p            # unmappable gearbox omitted, not sent raw
    assert "color" not in p              # unmappable color omitted, not sent raw
    assert "gearbox:spaceship" in unmapped
    assert "color:Fjord Blue" in unmapped


def test_push_normalizes_pollution_standard_label_to_slug():
    # euro_standard holds both slugs ('euro-6d') and labels ('Euro 6d'); each
    # resolves through an explicit map entry to the Autovit slug. Exact wire
    # format is confirmed by the publish read-back (_verify_advert
    # params_dropped) — see DATE/euro notes.
    def _poll(stored, target=None):
        # Map key is folded — resolve() folds `stored` the same way a
        # DB-backed map already is.
        tmap = {'pollution_standard': {(fold(stored), None): {'target_code': target, 'target_label': target}}} \
            if target else {}
        return tx.vehicle_to_advert({"brand": "Audi", "model": "A4",
                                     "euro_standard": stored}, {}, tmap)[0]["params"].get("pollution_standard")
    assert _poll("Euro 6d", "euro-6d") == "euro-6d"
    assert _poll("euro-6", "euro-6") == "euro-6"
    assert _poll("Euro 5", "euro-5") == "euro-5"
    # EVs have no pollution standard / no map entry — don't send a bogus value.
    assert _poll("N/A (EV)") is None


def test_push_preserves_already_slug_values():
    # Rows that already store Autovit slugs must pass through unchanged (no
    # double-mapping, no regression for Autovit-imported cars) — an identity
    # map entry resolves each slug to itself (color's real wire quirk aside).
    v = {"brand": "Audi", "model": "A4",
         "fuel_type": "plugin-hybrid", "transmission": "automatic",
         "drive_type": "all-wheel-permanent", "body_type": "suv",
         "color_exterior": "grey"}
    tmap = {
        'fuel_type': {('plugin-hybrid', None): {'target_code': 'plugin-hybrid', 'target_label': 'PHEV'}},
        'gearbox': {('automatic', None): {'target_code': 'automatic', 'target_label': 'Automatic'}},
        'drive': {('all-wheel-permanent', None): {'target_code': 'all-wheel-permanent', 'target_label': 'AWD'}},
        'body_type': {('suv', None): {'target_code': 'suv', 'target_label': 'SUV'}},
        'color': {('grey', None): {'target_code': 'gray', 'target_label': 'Gray'}},
    }
    p = tx.vehicle_to_advert(v, {}, tmap)[0]["params"]
    assert p["fuel_type"] == "plugin-hybrid"
    assert p["gearbox"] == "automatic"
    assert p["transmission"] == "all-wheel-permanent"
    assert p["body_type"] == "suv"
    assert p["color"] == "gray"


def test_validate_flags_missing_required():
    missing = tx.validate_for_publish({"category_id": 29, "params": {}})
    assert "params.make" in missing and "params.price" in missing


def test_validate_mileage_zero_is_not_missing():
    # mileage=0 is legitimate (a new car) and must NOT be flagged missing by a
    # naive truthy check; only absent / None / "" counts as missing.
    advert = {
        "title": "New Car", "category_id": 29,
        "params": {"make": "skoda", "model": "kodiaq", "year": 2025,
                   "mileage": 0, "fuel_type": "petrol", "body_type": "suv",
                   "color": "grey",
                   "price": {"1": 30000, "currency": "EUR"},
                   "vin": "TMBJK7NS0K8000099"},
    }
    missing = tx.validate_for_publish(advert)
    assert "params.mileage" not in missing
    assert missing == []
