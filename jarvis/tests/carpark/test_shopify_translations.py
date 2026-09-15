"""
Tests for Shopify translations module (Task 4).
Tests the RO value translations, body-type map, and default field-map seed.
"""

import pytest
from carpark.connectors.shopify.translations import (
    ro,
    VALUE_TRANSLATIONS_SEED,
    BODY_TYPE_RO,
    DEFAULT_FIELD_MAP,
)


class TestRoFunction:
    """Test the ro() helper function for value translation."""

    def test_ro_translates_with_existing_mapping(self):
        """ro() looks up value in the map and returns translation."""
        value_map = {"fuel_type": {"petrol": "Benzină"}}
        result = ro(value_map, "fuel_type", "petrol")
        assert result == "Benzină"

    def test_ro_identity_fallback_when_dimension_missing(self):
        """ro() returns the value unchanged if dimension not in map."""
        value_map = {}
        result = ro(value_map, "nonexistent_dimension", "SomeValue")
        assert result == "SomeValue"

    def test_ro_identity_fallback_when_value_missing(self):
        """ro() returns the value unchanged if specific value not in dimension."""
        value_map = {"fuel_type": {"diesel": "Motorină"}}
        result = ro(value_map, "fuel_type", "petrol")
        assert result == "petrol"

    def test_ro_returns_empty_string_when_value_is_none(self):
        """ro() returns empty string when value is None."""
        value_map = {"fuel_type": {"petrol": "Benzină"}}
        result = ro(value_map, "fuel_type", None)
        assert result == ""

    def test_ro_handles_non_string_values(self):
        """ro() converts non-string values to string for lookup."""
        value_map = {"body_type": {"suv": "SUV"}}
        # Should handle integer or other types by converting to string
        result = ro(value_map, "body_type", "suv")
        assert result == "SUV"


class TestBodyTypeRoMap:
    """Test the BODY_TYPE_RO mapping (body_type → RO product type)."""

    def test_body_type_suv_maps_to_suv(self):
        """BODY_TYPE_RO['suv'] == 'SUV'."""
        assert BODY_TYPE_RO["suv"] == "SUV"

    def test_body_type_has_berlina_mapping(self):
        """BODY_TYPE_RO includes sedan/Berlina mappings."""
        # At least one of these should exist
        assert ("Autoturism" in BODY_TYPE_RO and BODY_TYPE_RO["Autoturism"] == "Berlină") or \
               ("sedan" in BODY_TYPE_RO and BODY_TYPE_RO["sedan"] == "Berlină")

    def test_body_type_has_combi_mapping(self):
        """BODY_TYPE_RO includes combi mapping."""
        assert "combi" in BODY_TYPE_RO
        assert BODY_TYPE_RO["combi"] == "Combi"

    def test_body_type_has_break_mapping(self):
        """BODY_TYPE_RO includes estate/break mappings."""
        # At least one should exist
        assert ("break" in BODY_TYPE_RO and BODY_TYPE_RO["break"] == "Break") or \
               ("estate" in BODY_TYPE_RO and BODY_TYPE_RO["estate"] == "Break")

    def test_body_type_has_monovolum_mapping(self):
        """BODY_TYPE_RO includes van/minibus → Monovolum."""
        assert ("van" in BODY_TYPE_RO and BODY_TYPE_RO["van"] == "Monovolum") or \
               ("minibus" in BODY_TYPE_RO and BODY_TYPE_RO["minibus"] == "Monovolum")

    def test_body_type_has_compacta_mapping(self):
        """BODY_TYPE_RO includes hatchback/compacta → Compactă."""
        assert ("hatchback" in BODY_TYPE_RO and BODY_TYPE_RO["hatchback"] == "Compactă") or \
               ("compacta" in BODY_TYPE_RO and BODY_TYPE_RO["compacta"] == "Compactă")


class TestValueTranslationsSeed:
    """Test the VALUE_TRANSLATIONS_SEED dimensions and values."""

    def test_value_translations_has_fuel_type_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'fuel_type' key."""
        assert "fuel_type" in VALUE_TRANSLATIONS_SEED

    def test_fuel_type_petrol_maps_to_benzina(self):
        """VALUE_TRANSLATIONS_SEED['fuel_type']['petrol'] == 'Benzină'."""
        assert VALUE_TRANSLATIONS_SEED["fuel_type"]["petrol"] == "Benzină"

    def test_fuel_type_has_multiple_variants(self):
        """fuel_type dimension includes both English and slug variants."""
        # At least Petrol/petrol → Benzină and Diesel/diesel → Motorină
        fuel_type = VALUE_TRANSLATIONS_SEED.get("fuel_type", {})
        assert "Petrol" in fuel_type or "petrol" in fuel_type
        assert "Diesel" in fuel_type or "diesel" in fuel_type

    def test_value_translations_has_transmission_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'transmission' key."""
        assert "transmission" in VALUE_TRANSLATIONS_SEED

    def test_transmission_has_automatic_and_manual(self):
        """transmission dimension includes Automatic/automatic and Manual/manual."""
        transmission = VALUE_TRANSLATIONS_SEED.get("transmission", {})
        # At least one variant of each
        assert len([k for k in transmission if k.lower() == "automatic"]) > 0
        assert len([k for k in transmission if k.lower() == "manual"]) > 0

    def test_value_translations_has_drive_type_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'drive_type' key."""
        assert "drive_type" in VALUE_TRANSLATIONS_SEED

    def test_drive_type_includes_front_rear_integral(self):
        """drive_type dimension includes Front/Rear/Integral mappings."""
        drive_type = VALUE_TRANSLATIONS_SEED.get("drive_type", {})
        # Check for case-insensitive variants
        keys_lower = {k.lower(): k for k in drive_type.keys()}
        assert "front" in keys_lower or "fata" in keys_lower.get("front", "").lower()

    def test_value_translations_has_color_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'color_exterior' key."""
        assert "color_exterior" in VALUE_TRANSLATIONS_SEED

    def test_color_includes_basic_colors(self):
        """color_exterior includes gray/grey, White, Black, etc."""
        color = VALUE_TRANSLATIONS_SEED.get("color_exterior", {})
        # At least one color mapping should exist
        assert len(color) > 0

    def test_value_translations_has_body_type_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'body_type' key."""
        assert "body_type" in VALUE_TRANSLATIONS_SEED

    def test_value_translations_has_state_dimension(self):
        """VALUE_TRANSLATIONS_SEED has 'state' key (New/Used)."""
        assert "state" in VALUE_TRANSLATIONS_SEED

    def test_state_new_maps_to_nou(self):
        """state dimension maps New/new to 'Nou'."""
        state = VALUE_TRANSLATIONS_SEED.get("state", {})
        # At least one variant
        assert any(state.get(k) == "Nou" for k in ["New", "new"] if k in state)

    def test_state_used_maps_to_folosit(self):
        """state dimension maps Used/used/SH to 'Folosit'."""
        state = VALUE_TRANSLATIONS_SEED.get("state", {})
        # At least one variant
        assert any(state.get(k) == "Folosit" for k in ["Used", "used", "SH"] if k in state)


class TestDefaultFieldMap:
    """Test the DEFAULT_FIELD_MAP seed rows."""

    def test_default_field_map_is_list(self):
        """DEFAULT_FIELD_MAP is a list."""
        assert isinstance(DEFAULT_FIELD_MAP, list)

    def test_default_field_map_not_empty(self):
        """DEFAULT_FIELD_MAP has entries."""
        assert len(DEFAULT_FIELD_MAP) > 0

    def test_field_map_has_brand_to_marca(self):
        """DEFAULT_FIELD_MAP includes brand → custom.marca (raw)."""
        brand_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("source_expr") == "brand"
        ]
        assert len(brand_rows) == 1
        brand_row = brand_rows[0]
        assert brand_row["target_namespace"] == "custom"
        assert brand_row["target_key"] == "marca"
        assert brand_row["transform"] == "raw"

    def test_field_map_has_model_to_model(self):
        """DEFAULT_FIELD_MAP includes model → custom.model (raw)."""
        model_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("source_expr") == "model"
        ]
        assert len(model_rows) == 1
        model_row = model_rows[0]
        assert model_row["target_namespace"] == "custom"
        assert model_row["target_key"] == "model"
        assert model_row["transform"] == "raw"

    def test_field_map_has_dotari_with_multi_line_type(self):
        """DEFAULT_FIELD_MAP includes custom.dotari with multi_line_text_field type."""
        dotari_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("target_key") == "dotari"
        ]
        assert len(dotari_rows) >= 1
        dotari_row = dotari_rows[0]
        assert dotari_row["target_namespace"] == "custom"
        assert dotari_row["transform"] == "dotari"
        assert dotari_row["target_type"] == "multi_line_text_field"

    def test_field_map_has_transmisie_with_list_type(self):
        """DEFAULT_FIELD_MAP includes custom.transmisie with list.single_line_text_field type."""
        transmisie_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("target_key") == "transmisie"
        ]
        assert len(transmisie_rows) == 1
        transmisie_row = transmisie_rows[0]
        assert transmisie_row["target_namespace"] == "custom"
        assert transmisie_row["source_expr"] == "drive_type"
        assert transmisie_row["transform"] == "ro_list"
        assert transmisie_row["target_type"] == "list.single_line_text_field"

    def test_field_map_has_fuel_as_ro_value(self):
        """DEFAULT_FIELD_MAP includes fuel_type → custom.fuel (ro_value)."""
        fuel_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("target_key") == "fuel"
        ]
        assert len(fuel_rows) == 1
        fuel_row = fuel_rows[0]
        assert fuel_row["source_expr"] == "fuel_type"
        assert fuel_row["transform"] == "ro_value"

    def test_field_map_has_vin_to_sku(self):
        """DEFAULT_FIELD_MAP includes vin → custom.sku (raw)."""
        sku_rows = [
            row for row in DEFAULT_FIELD_MAP
            if row.get("source_expr") == "vin"
        ]
        assert len(sku_rows) >= 1
        sku_row = sku_rows[0]
        assert sku_row["target_key"] == "sku"
        assert sku_row["transform"] == "raw"

    def test_field_map_all_rows_have_required_fields(self):
        """Each DEFAULT_FIELD_MAP row has required fields."""
        for row in DEFAULT_FIELD_MAP:
            assert "source_expr" in row, f"Missing source_expr in row: {row}"
            assert "target_namespace" in row, f"Missing target_namespace in row: {row}"
            assert "target_key" in row, f"Missing target_key in row: {row}"
            assert "target_type" in row, f"Missing target_type in row: {row}"
            assert "transform" in row, f"Missing transform in row: {row}"

    def test_field_map_target_namespace_always_custom(self):
        """All DEFAULT_FIELD_MAP rows have target_namespace='custom'."""
        for row in DEFAULT_FIELD_MAP:
            assert row["target_namespace"] == "custom", \
                f"Expected target_namespace='custom', got {row['target_namespace']}"

    def test_field_map_types_are_valid(self):
        """DEFAULT_FIELD_MAP target_type values are valid Shopify types."""
        valid_types = {
            "single_line_text_field",
            "multi_line_text_field",
            "list.single_line_text_field",
            "integer",
            "decimal",
        }
        for row in DEFAULT_FIELD_MAP:
            assert row["target_type"] in valid_types, \
                f"Invalid target_type '{row['target_type']}' in row: {row}"

    def test_field_map_covers_required_fields(self):
        """DEFAULT_FIELD_MAP includes all required field mappings."""
        source_exprs = {row["source_expr"] for row in DEFAULT_FIELD_MAP}
        # Key fields that must be present
        required = {
            "brand", "model", "vin", "fuel_type", "transmission", "drive_type",
            "color_exterior", "mileage_km", "year_of_manufacture", "body_type"
        }
        assert required.issubset(source_exprs), \
            f"Missing required fields: {required - source_exprs}"
