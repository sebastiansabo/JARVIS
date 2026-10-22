"""Autovit ⇄ CarPark taxonomy — pure, bidirectional, no I/O.

Slug maps mirror frontend/src/data/autovitData.ts. API advert `params` use
lowercase slugs; a few differ from JARVIS canonical values (gray→grey, bej→beige).
"""
from typing import Any, Dict, List, Optional, Tuple

from . import taxonomy_map as _taxonomy_map

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


# ── Push-side value normalisation ──────────────────────────────────────────
# carpark_vehicles does NOT guarantee Autovit slugs: a 2026-10-15 data audit
# found the enum columns hold a mix of slugs, Romanian labels ("Automat",
# "Benzină", "Negru"), short forms ("fwd", "awd") and free text ("Fjord Blue").
# vehicle_to_advert previously pushed these RAW, so Autovit silently dropped any
# non-slug value and the advert field rendered blank. Each enum is now folded to
# its API slug (accept slug OR known RO-label/alias; unmappable -> omit, except
# colour which degrades to the real "other" slug so a colour still shows).

def _fold(value: Any) -> str:
    """lower + strip + strip Romanian diacritics, for tolerant matching."""
    s = str(value).strip().lower()
    for a, b in (("ă", "a"), ("â", "a"), ("î", "i"), ("ș", "s"), ("ş", "s"),
                 ("ț", "t"), ("ţ", "t")):
        s = s.replace(a, b)
    return s


# _fold()ed RO-label / common-variant -> Autovit API slug, per enum.
_FUEL_ALIASES = {
    "benzina": "petrol", "motorina": "diesel", "hibrid": "hybrid",
    "hibrid plug-in": "plugin-hybrid", "mild hybrid benzina": "mild-hybrid-petrol",
    "mild hybrid diesel": "mild-hybrid-diesel", "benzina + gpl": "petrol-lpg",
    "benzina + cng": "petrol-cng", "hidrogen": "hydrogen", "etanol": "ethanol",
}
_GEARBOX_ALIASES = {
    "manuala": "manual", "automata": "automatic", "automat": "automatic",
    "cutie automata": "automatic", "dual-clutch": "automatic", "dsg": "automatic",
    "cvt": "automatic", "semi-automata": "automatic", "tiptronic": "automatic",
}
_DRIVE_ALIASES = {
    "fata (fwd)": "front-wheel", "fwd": "front-wheel", "fata": "front-wheel",
    "spate (rwd)": "rear-wheel", "rwd": "rear-wheel", "spate": "rear-wheel",
    "4x4 permanent (awd)": "all-wheel-permanent", "awd": "all-wheel-permanent",
    "4x4": "all-wheel-permanent", "4wd": "all-wheel-permanent",
    "4x4 permanent": "all-wheel-permanent", "4x4 automat": "all-wheel-auto",
    "4x4 blocabil": "all-wheel-lock",
}
_BODY_ALIASES = {
    "off-road (suv)": "suv", "break": "combi", "compacta": "compact",
    "hatchback": "compact", "monovolum": "minivan", "masina de oras": "city-car",
    "masina mica": "small-car", "pick-up": "pickup", "van / utilitara": "van",
    "van/utilitara": "van", "utilitara": "van", "berlina": "sedan",
}
# RO label -> carpark canonical colour (then _REVERSE maps that to the API slug).
_COLOR_ALIASES = {
    "negru": "black", "alb": "white", "argintiu": "silver", "gri": "grey",
    "albastru": "blue", "rosu": "red", "verde": "green", "maro": "brown",
    "bej": "beige", "galben": "yellow", "portocaliu": "orange", "auriu": "gold",
    "violet / mov": "violet", "mov": "violet", "bordo": "bordeaux", "roz": "pink",
    "alta culoare": "other",
}

_FUEL_SLUGS = set(FUEL_MAP)
_GEARBOX_SLUGS = set(GEARBOX_MAP)
_DRIVE_SLUGS = set(DRIVE_MAP)
_BODY_SLUGS = set(BODY_MAP) | set(BODY_MAP.values())
_COLOR_SLUGS = set(COLOR_MAP.values())        # carpark canonical colours

# Autovit pollution-standard slugs (mirror AUTOVIT_EURO_STANDARDS in
# frontend/src/data/autovitData.ts). The exact wire value is confirmed per
# publish via _verify_advert's params_dropped read-back; if Autovit turns out to
# want a different form, flip these in one place. "N/A (EV)" & unknowns -> None.
_EURO_SLUGS = {"euro-6d", "euro-6d-temp", "euro-6c", "euro-6", "euro-5",
               "euro-4", "euro-3", "euro-2", "euro-1", "non-euro"}
_EURO_ALIASES = {
    "euro 6d": "euro-6d", "euro6d": "euro-6d", "euro 6d-temp": "euro-6d-temp",
    "euro 6c": "euro-6c", "euro 6": "euro-6", "euro6": "euro-6",
    "euro 5": "euro-5", "euro5": "euro-5", "euro 4": "euro-4", "euro4": "euro-4",
    "euro 3": "euro-3", "euro 2": "euro-2", "euro 1": "euro-1",
    "non euro": "non-euro", "noneuro": "non-euro",
}


def _norm_enum(value: Any, slugs: set, aliases: Dict[str, str],
               default: Any = None) -> Any:
    """carpark stored enum value -> Autovit slug. Accepts an exact slug
    (case-insensitive) or a known RO-label/variant; returns `default` (usually
    None, i.e. omit the param) when nothing matches. Absent/blank -> None."""
    if value is None:
        return None
    key = _fold(value)
    if not key:
        return None
    if key in slugs:
        return key
    return aliases.get(key, default)

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

    # Params Autovit sends that map to existing JARVIS columns but were previously
    # discarded on import (date_registration is intentionally omitted — its format
    # is unconfirmed and first_registration_date is a strict DATE column).
    if p.get("pollution_standard"):
        v["euro_standard"] = str(p["pollution_standard"]).strip()
    if p.get("country_origin"):
        v["country_of_origin"] = str(p["country_origin"]).strip()
    if "historical_vehicle" in p:
        v["is_vintage"] = _flag(p, "historical_vehicle")

    # equipment: every non-core 0/1 flag
    equip = {k: True for k, val in p.items()
             if k not in _CORE_PARAMS and str(val).strip() in ("1", "true", "yes")}
    if equip:
        v["equipment"] = equip

    return {k: val for k, val in v.items() if val is not None and val != ""}


# Autovit's /api/open (OLX Group "Motors" engine) carries first registration in
# `params` as a YEAR-FIRST dashed string, "YYYY-MM-DD" — confirmed via the
# Standvirtual/OTOMOTO open-API spec example value "2003-3-01". The old
# "DD/MM/YYYY" was rejected with 400 "Wrong format on 'date_registration'".
DATE_REGISTRATION_FORMAT = "%Y-%m-%d"


def _format_date_registration(value: Any) -> str:
    """carpark first_registration_date (date | ISO 'YYYY-MM-DD' str | None)
    -> Autovit date_registration string, or '' when absent/unparseable."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime(DATE_REGISTRATION_FORMAT)
    s = str(value).strip()[:10]
    try:
        from datetime import date
        return date.fromisoformat(s).strftime(DATE_REGISTRATION_FORMAT)
    except ValueError:
        return ""


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
REQUIRED_PARAMS = ("make", "model", "year", "mileage", "fuel_type", "price", "body_type", "color")


def vehicle_to_advert(vehicle: Dict[str, Any], account: Dict[str, Any],
                      taxonomy_map: Dict[str, Dict[Tuple[Any, Optional[str]], dict]]
                      ) -> Tuple[Dict[str, Any], List[str]]:
    """CarPark vehicle + Autovit account config + taxonomy map -> (advert, unmapped).

    Every CarPark enum/equipment value is resolved against the DB-confirmed
    `taxonomy_map` (Tasks 1-3) via `taxonomy_map.resolve()`/`emit()` — no
    alias-table guessing. `_norm_enum`/`_label_to_slug` (kept below, used by
    Task 4's seed and `advert_to_vehicle`) are no longer called from this
    function, and equipment is no longer pushed via a raw loop over every
    0/1-ish param: a miss is OMITTED from `params` (never raw-sent, since
    Autovit silently drops anything that isn't one of its exact codes) and
    recorded in `unmapped` as `"<dimension>:<source_value>"`.

    `model` is resolved SCOPED by the RESOLVED Autovit make code: `make` is
    resolved first, and its `target_code` (e.g. 'Audi' -> 'audi') becomes
    the make key for the `model` lookup. If `make` misses (or is absent),
    `model` is reported unmapped too — never resolved against the raw
    CarPark brand or falling back to some other make's entry.

    Pure: no I/O, no network calls — just dict shaping over the map it's
    handed.
    """
    cfg = (account or {}).get("config", {}) or {}
    params: Dict[str, Any] = {}
    unmapped: List[str] = []

    def _emit(dimension: str, source_value: Any,
              make: Optional[str] = None) -> Optional[str]:
        """Resolve `source_value` under `dimension` (+ `make` for the
        make-scoped `model` dimension) and emit it into `params` on a hit;
        record a miss in `unmapped` and return None. A blank/absent
        source_value is skipped silently (nothing to resolve)."""
        if source_value is None or source_value == "":
            return None
        hit = _taxonomy_map.resolve(taxonomy_map, dimension, source_value, make)
        if hit is None:
            unmapped.append(f"{dimension}:{source_value}")
            return None
        _taxonomy_map.emit(params, dimension, hit["target_code"])
        return hit["target_code"]

    if vehicle.get("vin"):
        params["vin"] = vehicle["vin"]

    resolved_make = _emit("make", vehicle.get("brand"))
    if vehicle.get("model"):
        if resolved_make is not None:
            _emit("model", vehicle["model"], make=resolved_make)
        else:
            # make is absent/unmapped -> model can't be scoped; report it
            # unmapped rather than guessing (no cross-make fallback).
            unmapped.append(f"model:{vehicle['model']}")

    if vehicle.get("year_of_manufacture"):
        params["year"] = vehicle["year_of_manufacture"]
    if vehicle.get("mileage_km") is not None:
        params["mileage"] = vehicle["mileage_km"]

    _emit("fuel_type", vehicle.get("fuel_type"))
    _emit("gearbox", vehicle.get("transmission"))
    # BUG-FIX-consistent: Autovit's param named "transmission" is drive type
    # (4x4/FWD/RWD), not gearbox — see advert_to_vehicle above; the `drive`
    # dimension's emit-kind (taxonomy_map.DIMENSIONS) writes to that param.
    _emit("drive", vehicle.get("drive_type"))
    _emit("body_type", vehicle.get("body_type"))
    _emit("color", vehicle.get("color_exterior"))
    _emit("pollution_standard", vehicle.get("euro_standard"))
    _emit("air_conditioning_type", vehicle.get("air_conditioning_type"))
    _emit("alloy_wheels_type", vehicle.get("alloy_wheels_type"))

    if vehicle.get("doors"):
        params["door_count"] = str(vehicle["doors"])
    if vehicle.get("engine_power_hp"):
        params["engine_power"] = vehicle["engine_power_hp"]
    if vehicle.get("engine_displacement_cc"):
        params["engine_capacity"] = vehicle["engine_displacement_cc"]
    if vehicle.get("current_price") is not None:
        # `gross_net` flags whether the price carries VAT, from the "Preț include
        # TVA" (price_includes_vat) checkbox: checked -> "gross" (VAT-inclusive),
        # unchecked -> "net". Absent defaults to "gross" (the DB column default is
        # TRUE). Autovit stores this verbatim (verified live) and it drives the
        # listing's net/TVA display — distinct from the `vat` invoice flag below.
        gross_net = "net" if vehicle.get("price_includes_vat") is False else "gross"
        params["price"] = {"1": vehicle["current_price"],
                           "currency": vehicle.get("price_currency", "EUR"),
                           "gross_net": gross_net}
    # VAT invoice flag ("factură cu TVA"), from the acquisition regime
    # (vat_deductible): normal regime (True) -> "1" (cu TVA); margin regime
    # (False) -> "0"; absent -> omitted. Verified live against the Autovit
    # create API (draft adverts): "1" stores as "1"; "0" is accepted and stored
    # as absent (== fără TVA, same as omitting) — no 400. This is the invoice
    # flag, distinct from the price's gross_net above (VAT-inclusive pricing).
    if vehicle.get("vat_deductible") is not None:
        params["vat"] = "1" if vehicle["vat_deductible"] else "0"
    # Optional attributes Autovit also supports (it SENDS them on pull) that push
    # previously dropped — emitted so the advert is fuller. SMOKE-TEST the create
    # contract (publish dry_run, then draft=True to upload a disabled advert)
    # before enabling in prod: an unexpected param could 400 the create.
    if vehicle.get("seats"):
        params["nr_seats"] = vehicle["seats"]
    if vehicle.get("co2_emissions") is not None:
        params["co2_emissions"] = vehicle["co2_emissions"]
    if vehicle.get("generation"):
        params["generation"] = str(vehicle["generation"])
    if vehicle.get("variant"):
        params["version"] = str(vehicle["variant"])
    # date_registration — sent in YYYY-MM-DD (see DATE_REGISTRATION_FORMAT);
    # the earlier DD/MM/YYYY value 400'd "Wrong format on 'date_registration'".
    date_reg = _format_date_registration(vehicle.get("first_registration_date"))
    if date_reg:
        params["date_registration"] = date_reg
    if vehicle.get("country_of_origin"):
        params["country_origin"] = str(vehicle["country_of_origin"]).strip()
    # Condition flags as Autovit "1"/"0" (mirrors advert_to_vehicle's _flag read).
    for autovit_param, vehicle_key in (
        ("registered", "is_registered"),
        ("original_owner", "is_first_owner"),
        ("service_record", "has_service_book"),
        ("tuning", "has_tuning"),
        ("historical_vehicle", "is_vintage"),
    ):
        if vehicle.get(vehicle_key) is not None:
            params[autovit_param] = "1" if vehicle[vehicle_key] else "0"
    if vehicle.get("has_accident_history") is not None:
        params["no_accident"] = "0" if vehicle["has_accident_history"] else "1"

    # Equipment: source values = UNNEST(equipment_options) ∪ truthy keys of
    # the `equipment` JSONB dict (both the editor's Dotări TEXT[] and the
    # legacy Autovit-imported flag dict feed the SAME 'equipment' dimension
    # resolve — not make-scoped, so `make=None`). A hit emits
    # params[<target_code>]="1" (taxonomy_map's 'flag' emit-kind); a miss is
    # omitted and reported, never raw-sent.
    equip_values = set()
    for slug in (vehicle.get("equipment_options") or []):
        if slug:
            equip_values.add(str(slug))
    for k, val in (vehicle.get("equipment") or {}).items():
        if val is True:
            equip_values.add(str(k))
    for source_value in sorted(equip_values):
        _emit("equipment", source_value)

    # Create-only conditional param Autovit requires for cars: not in the
    # category "required" list, but POST /account/adverts rejects its absence
    # ("params.is_imported_car ... obligatoriu"). Verified live 2026-09-09.
    params.setdefault("is_imported_car", "0")

    advert: Dict[str, Any] = {
        "title": vehicle.get("listing_title")
                 or f"{vehicle.get('brand', '')} {vehicle.get('model', '')}".strip(),
        "description": vehicle.get("listing_description") or "",
        "category_id": CARS_CATEGORY_ID,
        "new_used": "new" if vehicle.get("state") == "Nou" else "used",
        "advertiser_type": cfg.get("advertiser_type", "business"),
        "params": params,
    }
    # Location + contact come from the account config; the publish route fills
    # these from the account's own existing adverts when not explicitly set.
    for key in ("region_id", "city_id", "district_id", "coordinates"):
        if cfg.get(key) is not None:
            advert[key] = cfg[key]
    person = cfg.get("contact_person")
    phones = cfg.get("phones") or ([cfg["phone"]] if cfg.get("phone") else [])
    if person or phones:
        # Autovit expects `contact.phones` (array), not `phone_numbers`.
        advert["contact"] = {"person": person or "", "phones": phones}
    return advert, unmapped


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
