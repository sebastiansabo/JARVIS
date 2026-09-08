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
