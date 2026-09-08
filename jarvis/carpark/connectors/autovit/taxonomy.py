"""Autovit ⇄ CarPark taxonomy — pure, bidirectional, no I/O.

Slug maps mirror frontend/src/data/autovitData.ts. API advert `params` use
lowercase slugs; a few differ from JARVIS canonical values (gray→grey, bej→beige).
"""
from typing import Any, Dict, List

CARS_CATEGORY_ID = 29

# api_slug -> carpark canonical value (identity unless noted)
FUEL_MAP = {s: s for s in ("petrol", "diesel", "electric", "hybrid",
                           "plugin-hybrid", "mild-hybrid-petrol",
                           "mild-hybrid-diesel", "petrol-lpg", "petrol-cng",
                           "hydrogen", "ethanol")}
BODY_MAP = {s: s for s in ("sedan", "combi", "suv", "coupe", "cabrio",
                           "compact", "minivan", "minibus", "city-car",
                           "small-car", "pickup", "van", "vans")}
BODY_MAP["vans"] = "van"
GEARBOX_MAP = {"manual": "manual", "automatic": "automatic"}
DRIVE_MAP = {s: s for s in ("front-wheel", "rear-wheel", "all-wheel-permanent",
                            "all-wheel-auto", "all-wheel-lock")}
COLOR_MAP = {s: s for s in ("black", "white", "silver", "blue", "red", "green",
                            "brown", "yellow", "orange", "gold", "violet",
                            "bordeaux", "pink", "other")}
COLOR_MAP["gray"] = "grey"
COLOR_MAP["bej"] = "beige"
COLOR_MAP["grey"] = "grey"
COLOR_MAP["beige"] = "beige"

_REVERSE = {  # carpark value -> api slug, for push
    "color": {v: k for k, v in COLOR_MAP.items() if k not in ("grey", "beige")},
}

# Non-equipment core params we map explicitly; everything else that is a 0/1
# flag becomes an equipment entry.
_CORE_PARAMS = {
    "vin", "make", "model", "year", "mileage", "fuel_type", "gearbox",
    "transmission", "body_type", "color", "door_count", "nr_seats",
    "engine_capacity", "engine_power", "co2_emissions", "pollution_standard",
    "date_registration", "generation", "version", "price", "vat",
    "financial_option", "registered", "no_accident", "damaged",
    "service_record", "original_owner", "tuning", "has_vin", "country_origin",
    "cepik_authorization", "historical_vehicle", "features",
}

MERGE_FIELDS = {
    "brand", "model", "variant", "generation", "body_type",
    "year_of_manufacture", "first_registration_date", "color_exterior",
    "fuel_type", "transmission", "drive_type", "engine_displacement_cc",
    "engine_power_hp", "co2_emissions", "euro_standard", "mileage_km",
    "doors", "seats", "is_registered", "is_first_owner", "has_accident_history",
    "has_service_book", "has_tuning", "is_electric_vehicle", "equipment",
    "listing_title", "listing_description", "current_price", "price_currency",
    "state",
}

# Params harvested into the `equipment` JSONB blob by advert_to_vehicle are
# simply "every non-core 0/1 flag" (open-ended, whatever Autovit sends) — see
# _CORE_PARAMS above and the harvesting loop in advert_to_vehicle. There is
# no fixed equipment-slug whitelist in this task's brief (Step 3 sample code
# does not define one), so EQUIPMENT_PARAMS is intentionally left undefined
# here; see the deviations note in task-1-report.md.


def slug_to_label(slug: str) -> str:
    """audi -> Audi ; range-rover-velar -> Range Rover Velar."""
    return " ".join(w.capitalize() for w in str(slug).replace("_", "-").split("-"))


def _flag(params: Dict[str, Any], key: str) -> bool:
    return str(params.get(key, "")).strip() in ("1", "true", "yes")


def _int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def advert_to_vehicle(advert: Dict[str, Any]) -> Dict[str, Any]:
    p = advert.get("params", {}) or {}
    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    fuel = FUEL_MAP.get(str(p.get("fuel_type") or "").strip())

    v: Dict[str, Any] = {
        "source": "autovit",
        "listing_title": advert.get("title", "") or None,
        "listing_description": advert.get("description", "") or None,
    }
    if p.get("vin"):
        v["vin"] = str(p["vin"]).strip().upper()
    if p.get("make"):
        v["brand"] = slug_to_label(p["make"])
    if p.get("model"):
        v["model"] = slug_to_label(p["model"])
    if p.get("generation"):
        v["generation"] = str(p["generation"])
    if p.get("version"):
        v["variant"] = str(p["version"])
    if _int(p.get("year")):
        v["year_of_manufacture"] = _int(p["year"])
    if _int(p.get("mileage")) is not None:
        v["mileage_km"] = _int(p["mileage"])
    if fuel:
        v["fuel_type"] = fuel
        v["is_electric_vehicle"] = fuel == "electric"
    if p.get("gearbox") in GEARBOX_MAP:
        v["transmission"] = GEARBOX_MAP[p["gearbox"]]
    if p.get("transmission") in DRIVE_MAP:              # BUG FIX: drive lives here
        v["drive_type"] = DRIVE_MAP[p["transmission"]]
    if p.get("body_type") in BODY_MAP:
        v["body_type"] = BODY_MAP[p["body_type"]]
    if p.get("color") in COLOR_MAP:
        v["color_exterior"] = COLOR_MAP[p["color"]]
    if _int(p.get("door_count")):
        v["doors"] = _int(p["door_count"])
    if _int(p.get("nr_seats")):
        v["seats"] = _int(p["nr_seats"])
    if _int(p.get("engine_capacity")):
        v["engine_displacement_cc"] = _int(p["engine_capacity"])
    if _int(p.get("engine_power")):
        v["engine_power_hp"] = _int(p["engine_power"])
    if _int(p.get("co2_emissions")):
        v["co2_emissions"] = _int(p["co2_emissions"])
    if price.get("1") is not None:
        try:
            v["current_price"] = float(price["1"])
        except (TypeError, ValueError):
            pass
        v["price_currency"] = price.get("currency", "EUR")
    if advert.get("new_used"):
        v["state"] = "Nou" if advert["new_used"] == "new" else "Rulat"

    # booleans
    if "registered" in p:
        v["is_registered"] = _flag(p, "registered")
    if "original_owner" in p:
        v["is_first_owner"] = _flag(p, "original_owner")
    if "no_accident" in p or "damaged" in p:
        v["has_accident_history"] = (not _flag(p, "no_accident")) or _flag(p, "damaged")
    if "service_record" in p:
        v["has_service_book"] = _flag(p, "service_record")
    if "tuning" in p:
        v["has_tuning"] = _flag(p, "tuning")

    # equipment: every non-core 0/1 flag
    equip = {k: True for k, val in p.items()
             if k not in _CORE_PARAMS and str(val).strip() in ("1", "true", "yes")}
    if equip:
        v["equipment"] = equip

    return {k: val for k, val in v.items() if val is not None and val != ""}
