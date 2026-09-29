from carpark.connectors.autovit import taxonomy as tx

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
    ad = tx.vehicle_to_advert(vehicle, account)
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


def test_vehicle_to_advert_pushes_equipment_options():
    # Form-entered equipment lives in equipment_options (TEXT[] of Autovit slugs);
    # each must become an Autovit "<slug>"="1" param. Previously only the JSONB
    # `equipment` dict was pushed, so form-entered dotări never reached Autovit.
    ad = tx.vehicle_to_advert(
        {"brand": "Audi", "model": "A4", "equipment_options": ["apple_carplay", "led_lights"]},
        {},
    )
    assert ad["params"].get("apple_carplay") == "1"
    assert ad["params"].get("led_lights") == "1"


def test_vehicle_to_advert_merges_equipment_dict_and_options():
    ad = tx.vehicle_to_advert(
        {"brand": "Audi", "model": "A4",
         "equipment": {"esp": True, "abs": False},
         "equipment_options": ["apple_carplay"]},
        {},
    )
    p = ad["params"]
    assert p.get("esp") == "1"            # JSONB True flag still pushed
    assert "abs" not in p                 # JSONB False flag not pushed
    assert p.get("apple_carplay") == "1"  # options slug pushed


def test_vehicle_to_advert_color_reverse_map():
    # PUSH: carpark canonical color -> live Autovit api slug. Only grey/beige
    # differ from identity (grey->gray, beige->bej); everything else is 1:1.
    def _color(c):
        return tx.vehicle_to_advert({"color_exterior": c}, {})["params"]["color"]
    assert _color("grey") == "gray"
    assert _color("beige") == "bej"
    assert _color("black") == "black"
    assert _color("red") == "red"


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
