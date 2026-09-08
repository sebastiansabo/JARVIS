"""Autovit ⇄ CarPark taxonomy — pure, bidirectional, no I/O.

Slug maps mirror frontend/src/data/autovitData.ts. API advert `params` use
lowercase slugs; a few differ from JARVIS canonical values (gray→grey, bej→beige).
"""
from typing import Any, Dict, List

CARS_CATEGORY_ID = 29

# Canonical brand names — mirrors AUTOVIT_BRANDS in
# frontend/src/data/autovitData.ts. These are the exact values the rest of the
# app stores in carpark_vehicles.brand, so advert_to_vehicle must emit them
# verbatim rather than a naive title-cased slug (which would give "Bmw",
# "Mercedes Benz", etc. and diverge from the picklist).
AUTOVIT_BRANDS = [
    "Abarth", "Acura", "Aiways", "Alfa Romeo", "Alpina", "Alpine",
    "Aston Martin", "Audi", "Baic", "Bentley", "BMW", "Bugatti", "Buick",
    "BYD", "Cadillac", "Caterham", "Chery", "Chevrolet", "Chrysler",
    "Citroen", "Cupra", "Dacia", "Daewoo", "Daihatsu", "DFSK", "Dodge",
    "DR", "DS", "Ferrari", "Fiat", "Ford", "Foton", "Genesis", "GMC",
    "Great Wall", "Honda", "Hummer", "Hyundai", "Ineos", "Infiniti",
    "Isuzu", "Iveco", "Jaecoo", "Jaguar", "Jeep", "Kia", "KTM", "Lada",
    "Lamborghini", "Lancia", "Land Rover", "Leapmotor", "Lexus", "Lincoln",
    "Lotus", "Lucid", "Lynk & Co", "Maserati", "Maxus", "Maybach", "Mazda",
    "McLaren", "Mercedes-Benz", "MG", "MINI", "Mitsubishi", "Morgan", "NIO",
    "Nissan", "Omoda", "Opel", "Peugeot", "Polestar", "Pontiac", "Porsche",
    "RAM", "Renault", "Rivian", "Rolls-Royce", "Rover", "Saab", "SEAT",
    "Seres", "Skoda", "Smart", "SsangYong", "Subaru", "Suzuki", "Tesla",
    "Toyota", "Trabant", "Volkswagen", "Volvo", "Voyah", "Wartburg",
    "XPeng", "Zeekr",
]


def _slugify(s: str) -> str:
    """'Mercedes-Benz' -> 'mercedes-benz'; 'Land Rover' -> 'land-rover'."""
    return str(s).strip().lower().replace(" ", "-")


# api_slug (make) -> canonical brand label
BRAND_LABELS = {_slugify(label): label for label in AUTOVIT_BRANDS}

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

# carpark color value -> Autovit api slug (push). Only grey/beige differ from
# identity: per LIVE Autovit data the real color param slugs are "gray"/"bej"
# (NOT "grey"/"beige"), so push must emit those. PULL (advert_to_vehicle) does
# the inverse via COLOR_MAP: api "gray"->carpark "grey", api "bej"->"beige".
# The two explicit overrides below are order-independent (they run after the
# comprehension), so which key iterates last in COLOR_MAP is irrelevant.
_REVERSE = {"color": {v: k for k, v in COLOR_MAP.items()}}
_REVERSE["color"]["grey"] = "gray"
_REVERSE["color"]["beige"] = "bej"

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
        make_slug = str(p["make"]).strip().lower()
        v["brand"] = BRAND_LABELS.get(make_slug) or slug_to_label(p["make"])
    if p.get("model"):
        v["model"] = slug_to_label(p["model"])
    if p.get("generation"):
        v["generation"] = str(p["generation"])
    if p.get("version"):
        v["variant"] = str(p["version"])
    if _int(p.get("year")) is not None:
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
    if _int(p.get("door_count")) is not None:
        v["doors"] = _int(p["door_count"])
    if _int(p.get("nr_seats")) is not None:
        v["seats"] = _int(p["nr_seats"])
    if _int(p.get("engine_capacity")) is not None:
        v["engine_displacement_cc"] = _int(p["engine_capacity"])
    if _int(p.get("engine_power")) is not None:
        v["engine_power_hp"] = _int(p["engine_power"])
    if _int(p.get("co2_emissions")) is not None:
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


def _label_to_slug(label: str) -> str:
    """'BMW' -> 'bmw'; 'Land Rover' -> 'land-rover'; 'Mercedes-Benz' -> 'mercedes-benz'.

    Same rule as _slugify (used to build BRAND_LABELS for the pull direction);
    kept as a separate name for the push direction so each direction reads
    with its own vocabulary, without duplicating the slugging logic.
    """
    return _slugify(label)


# Advert params that must be present (truthy) for a publish attempt to
# Autovit to be worth sending. Not exhaustive of everything Autovit requires
# server-side — just the fields CarPark can check locally before calling out.
REQUIRED_PARAMS = ("make", "model", "year", "mileage", "fuel_type", "price", "vin")


def vehicle_to_advert(vehicle: Dict[str, Any], account: Dict[str, Any]) -> Dict[str, Any]:
    """CarPark vehicle + Autovit account config -> Autovit advert payload (push).

    Inverse of advert_to_vehicle for the fields both directions share. Pure:
    no I/O, no network calls — just dict shaping.
    """
    cfg = (account or {}).get("config", {}) or {}
    params: Dict[str, Any] = {}
    if vehicle.get("vin"):
        params["vin"] = vehicle["vin"]
    if vehicle.get("brand"):
        params["make"] = _label_to_slug(vehicle["brand"])
    if vehicle.get("model"):
        params["model"] = _label_to_slug(vehicle["model"])
    if vehicle.get("year_of_manufacture"):
        params["year"] = vehicle["year_of_manufacture"]
    if vehicle.get("mileage_km") is not None:
        params["mileage"] = vehicle["mileage_km"]
    if vehicle.get("fuel_type"):
        params["fuel_type"] = vehicle["fuel_type"]
    if vehicle.get("transmission"):
        params["gearbox"] = vehicle["transmission"]
    if vehicle.get("drive_type"):
        # BUG-FIX-consistent: Autovit's param named "transmission" is drive
        # type (4x4/FWD/RWD), not gearbox — see advert_to_vehicle above.
        params["transmission"] = vehicle["drive_type"]
    if vehicle.get("body_type"):
        params["body_type"] = vehicle["body_type"]
    if vehicle.get("color_exterior"):
        params["color"] = _REVERSE["color"].get(vehicle["color_exterior"], vehicle["color_exterior"])
    if vehicle.get("doors"):
        params["door_count"] = str(vehicle["doors"])
    if vehicle.get("engine_power_hp"):
        params["engine_power"] = vehicle["engine_power_hp"]
    if vehicle.get("engine_displacement_cc"):
        params["engine_capacity"] = vehicle["engine_displacement_cc"]
    if vehicle.get("current_price") is not None:
        params["price"] = {"1": vehicle["current_price"],
                           "currency": vehicle.get("price_currency", "EUR")}
    for k, val in (vehicle.get("equipment") or {}).items():
        if val is True:
            params[k] = "1"

    advert: Dict[str, Any] = {
        "title": vehicle.get("listing_title")
                 or f"{vehicle.get('brand', '')} {vehicle.get('model', '')}".strip(),
        "description": vehicle.get("listing_description") or "",
        "category_id": CARS_CATEGORY_ID,
        "new_used": "new" if vehicle.get("state") == "Nou" else "used",
        "params": params,
    }
    if cfg.get("city_id"):
        advert["city_id"] = cfg["city_id"]
    if cfg.get("region_id"):
        advert["region_id"] = cfg["region_id"]
    if cfg.get("contact_person") or cfg.get("phone"):
        advert["contact"] = {"person": cfg.get("contact_person", ""),
                             "phone_numbers": [cfg["phone"]] if cfg.get("phone") else []}
    return advert


def validate_for_publish(advert: Dict[str, Any]) -> List[str]:
    """Return the list of missing required fields/params ('' if publishable)."""
    missing: List[str] = []
    if not advert.get("title"):
        missing.append("title")
    if not advert.get("category_id"):
        missing.append("category_id")
    p = advert.get("params", {}) or {}
    for req in REQUIRED_PARAMS:
        val = p.get(req)
        # A real 0 (e.g. mileage=0 on a new car) or a present price dict is
        # valid — only an absent key, None, or "" counts as missing.
        if val is None or val == "":
            missing.append(f"params.{req}")
    return missing
