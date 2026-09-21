"""
Shopify schema translations: RO value mappings, body-type vocabulary, and default field map.
Consumed by Task 5 (mapper) and seeded into DB.
"""

from typing import Dict, List, Optional


def ro(value_map: Dict[str, Dict[str, str]], dimension: str, value) -> str:
    """
    Translate a CarPark value to Romanian using the value map.

    Args:
        value_map: Dict[dimension][source_value] = ro_value
        dimension: The dimension key (e.g., 'fuel_type', 'transmission')
        value: The source value to translate (or already-RO fallback)

    Returns:
        Translated RO value, or the original value if no translation found (identity fallback).
        Returns empty string if value is None.
    """
    if value is None:
        return ""

    value_str = str(value)
    dimension_map = value_map.get(dimension, {})
    return dimension_map.get(value_str, value_str)


# RO value translations, seeded from mobile.de VALUE_TRANSLATIONS.
# Each dimension maps CarPark source values (both English words and lowercase slugs) to Romanian.
VALUE_TRANSLATIONS_SEED: Dict[str, Dict[str, str]] = {
    "fuel_type": {
        # The Autoworld store's `custom.fuel` metafield is a CHOICE LIST — the pushed
        # value MUST be one of: Benzină / Benzină (Mild-Hybrid) / Diesel /
        # Diesel (Mild-Hybrid) / Hybrid / Plug-in Hybrid / Electric / LPG, else Shopify
        # rejects publish ("Value does not exist in provided choices"). So these map to
        # the store's exact vocabulary — NOT the generic RO words (Motorină/Hibrid/GPL).
        # Keys cover the canonical Autovit FUEL_MAP slugs (autovit/taxonomy.py) plus
        # legacy/manual variants. NOTE: petrol-cng / hydrogen / ethanol have no store
        # choice yet — publishing such a car fails until a matching choice is added.
        "petrol": "Benzină",
        "Petrol": "Benzină",
        "Benzina": "Benzină",
        "benzina": "Benzină",
        "diesel": "Diesel",
        "Diesel": "Diesel",
        "electric": "Electric",
        "Electric": "Electric",
        "hybrid": "Hybrid",
        "Hybrid": "Hybrid",
        "Hibrid": "Hybrid",
        "mild-hybrid-diesel": "Diesel (Mild-Hybrid)",
        "mild-hybrid-petrol": "Benzină (Mild-Hybrid)",
        "mild-hybrid-benzina": "Benzină (Mild-Hybrid)",
        "plugin-hybrid": "Plug-in Hybrid",
        "plug-in-hybrid": "Plug-in Hybrid",
        "Hibrid Plug-In": "Plug-in Hybrid",
        "petrol-lpg": "LPG",
        "LPG": "LPG",
        "lpg": "LPG",
        "GPL": "LPG",
    },
    "transmission": {
        "Automatic": "Automată",
        "automatic": "Automată",
        "Automata": "Automată",  # Common misspelling
        "automata": "Automată",
        "Manual": "Manuală",
        "manual": "Manuală",
        "Manuala": "Manuală",  # Common misspelling
        "manuala": "Manuală",
        "CVT": "CVT",
        "cvt": "CVT",
    },
    "drive_type": {
        "Front": "Față",
        "front": "Față",
        "Front-wheel": "Față",
        "front-wheel": "Față",
        "Rear": "Spate",
        "rear": "Spate",
        "Rear-wheel": "Spate",
        "rear-wheel": "Spate",
        "All-wheel": "Integral",
        "all-wheel": "Integral",
        "4x4": "Integral",
        "4WD": "Integral",
        "AWD": "Integral",
        "Integral": "Integral",
        "integral": "Integral",
    },
    "color_exterior": {
        "White": "Alb",
        "white": "Alb",
        "Black": "Negru",
        "black": "Negru",
        "Gray": "Gri",
        "gray": "Gri",
        "Grey": "Gri",
        "grey": "Gri",
        "Blue": "Albastru",
        "blue": "Albastru",
        "Red": "Roșu",
        "red": "Roșu",
        "Silver": "Argintiu",
        "silver": "Argintiu",
        "Green": "Verde",
        "green": "Verde",
        "Brown": "Maro",
        "brown": "Maro",
        "Yellow": "Galben",
        "yellow": "Galben",
        "Orange": "Portocaliu",
        "orange": "Portocaliu",
        "Purple": "Mov",
        "purple": "Mov",
        "Beige": "Bej",
        "beige": "Bej",
        "Gold": "Auriu",
        "gold": "Auriu",
    },
    "body_type": {
        "SUV": "SUV",
        "suv": "SUV",
        "Sedan": "Berlină",
        "sedan": "Berlină",
        "Autoturism": "Berlină",
        "autoturism": "Berlină",
        "Saloon": "Berlină",
        "saloon": "Berlină",
        "Combi": "Combi",
        "combi": "Combi",
        "Estate": "Break",
        "estate": "Break",
        "Break": "Break",
        "break": "Break",
        "Van": "Monovolum",
        "van": "Monovolum",
        "Minibus": "Monovolum",
        "minibus": "Monovolum",
        "Autoutilitară": "Monovolum",
        "autoutilitara": "Monovolum",
        "Hatchback": "Compactă",
        "hatchback": "Compactă",
        "Compacta": "Compactă",
        "compacta": "Compactă",
        "Coupe": "Coupé",
        "coupe": "Coupé",
        "Cabrio": "Cabrio",
        "cabrio": "Cabrio",
        "Cabriolet": "Cabrio",
        "cabriolet": "Cabrio",
        "Roadster": "Cabrio",
        "roadster": "Cabrio",
        "Pickup": "Pickup",
        "pickup": "Pickup",
    },
    "state": {
        "New": "Nou",
        "new": "Nou",
        "Used": "Folosit",
        "used": "Folosit",
        "SH": "Folosit",
        "sh": "Folosit",
    },
}

# RO body-type product type vocabulary.
# Maps CarPark body_type/vehicle_type values to store's RO productType vocabulary.
# Derived from VALUE_TRANSLATIONS_SEED["body_type"] (single source of truth) so the
# two never drift; any productType-only extras can be merged in here.
BODY_TYPE_RO: Dict[str, str] = {
    **dict(VALUE_TRANSLATIONS_SEED["body_type"]),
    # <productType-only extras (not in VALUE_TRANSLATIONS_SEED["body_type"]) go here>
}

# Default field map seed rows (carpark source → custom.* metafield).
# Each row maps a CarPark field/derivation to a Shopify custom metafield with transform.
# Consumed by Task 5 (mapper) and seeded into carpark_shopify_field_map table.
DEFAULT_FIELD_MAP: List[dict] = [
    {
        "source_expr": "brand",
        "target_namespace": "custom",
        "target_key": "marca",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
    {
        "source_expr": "model",
        "target_namespace": "custom",
        "target_key": "model",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
    {
        "source_expr": "vin",
        "target_namespace": "custom",
        "target_key": "sku",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
    {
        "source_expr": "fuel_type",
        "target_namespace": "custom",
        "target_key": "fuel",
        "target_type": "single_line_text_field",
        "transform": "ro_value",
    },
    {
        "source_expr": "transmission",
        "target_namespace": "custom",
        "target_key": "cutie_viteze",
        "target_type": "single_line_text_field",
        "transform": "ro_value",
    },
    {
        "source_expr": "drive_type",
        "target_namespace": "custom",
        "target_key": "transmisie",
        "target_type": "list.single_line_text_field",
        "transform": "ro_list",
    },
    {
        "source_expr": "color_exterior",
        "target_namespace": "custom",
        "target_key": "culoare",
        "target_type": "single_line_text_field",
        "transform": "ro_value",
    },
    {
        "source_expr": "color_interior",
        "target_namespace": "custom",
        "target_key": "culoare_tapiterie",
        "target_type": "single_line_text_field",
        "transform": "ro_value",
    },
    {
        "source_expr": "mileage_km",
        "target_namespace": "custom",
        "target_key": "kilometraj",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "engine_displacement_cc",
        "target_namespace": "custom",
        "target_key": "cilindree",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "engine_power_hp",
        "target_namespace": "custom",
        "target_key": "putere_cp",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "engine_power_kw",
        "target_namespace": "custom",
        "target_key": "putere_kw",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "year_of_manufacture",
        "target_namespace": "custom",
        "target_key": "anul_modelului",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "first_registration_date",
        "target_namespace": "custom",
        "target_key": "data_livrarii",
        "target_type": "single_line_text_field",
        "transform": "year",
    },
    {
        "source_expr": "body_type",
        "target_namespace": "custom",
        "target_key": "body_type",
        "target_type": "single_line_text_field",
        "transform": "ro_value",
    },
    {
        "source_expr": "doors",
        "target_namespace": "custom",
        "target_key": "nr_de_usi",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "euro_standard",
        "target_namespace": "custom",
        "target_key": "clasa_de_emisii_noxe",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
    {
        "source_expr": "co2_emissions",
        "target_namespace": "custom",
        "target_key": "emisii_co2",
        "target_type": "single_line_text_field",
        "transform": "int",
    },
    {
        "source_expr": "equipment_level",
        "target_namespace": "custom",
        "target_key": "nivel_de_echipare",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
    {
        "source_expr": "equipment + optional_packages",
        "target_namespace": "custom",
        "target_key": "dotari",
        "target_type": "multi_line_text_field",
        "transform": "dotari",
    },
    {
        "source_expr": "registration_number",
        "target_namespace": "custom",
        "target_key": "nr_imatr_",
        "target_type": "single_line_text_field",
        "transform": "raw",
    },
]
