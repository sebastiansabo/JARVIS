"""Abstract base provider and VehicleSpecs dataclass.

VehicleSpecs is the unified output format for all VIN decoder providers.
BaseVINProvider is the ABC that each provider must implement.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class VehicleSpecs:
    """Unified vehicle specification result from any VIN decoder provider."""

    # Source
    provider: str = ''
    raw_response: Dict[str, Any] = field(default_factory=dict, repr=False)
    decoded_at: datetime = field(default_factory=datetime.utcnow)

    # Identity
    vin: str = ''
    brand: str = ''
    model: str = ''
    variant: str = ''
    generation: str = ''
    model_year: int = 0
    manufacture_year: int = 0

    # Body
    body_type: str = ''
    doors: int = 0
    seats: int = 0
    color: str = ''

    # Engine
    fuel_type: str = ''
    engine_displacement_cc: int = 0
    engine_power_hp: int = 0
    engine_power_kw: int = 0
    engine_code: str = ''
    cylinders: int = 0

    # Transmission
    transmission: str = ''
    transmission_detail: str = ''
    drive_type: str = ''
    gears: int = 0

    # Dimensions & Weight
    length_mm: int = 0
    width_mm: int = 0
    height_mm: int = 0
    wheelbase_mm: int = 0
    curb_weight_kg: int = 0
    gross_weight_kg: int = 0

    # Performance
    max_speed_kmh: int = 0
    acceleration_0_100: float = 0.0

    # Fuel & Emissions
    fuel_consumption_combined: float = 0.0
    fuel_tank_capacity: float = 0.0
    co2_emissions: int = 0
    euro_standard: str = ''
    battery_capacity_kwh: float = 0.0

    # Manufacturing
    manufacturer: str = ''
    plant_country: str = ''
    plant_city: str = ''
    produced_from: str = ''
    produced_to: str = ''

    # Equipment
    equipment: List[str] = field(default_factory=list)
    standard_equipment: List[str] = field(default_factory=list)
    optional_equipment: List[str] = field(default_factory=list)

    # Confidence
    confidence_score: float = 0.0
    fields_decoded: int = 0
    fields_total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization. Strips raw_response."""
        d = asdict(self)
        d['decoded_at'] = self.decoded_at.isoformat() if self.decoded_at else None
        d.pop('raw_response', None)
        return d

    def to_vehicle_fields(self) -> Dict[str, Any]:
        """Map to carpark_vehicles table columns for auto-population."""
        fields = {}
        if self.brand:
            fields['brand'] = self.brand
        if self.model:
            fields['model'] = self.model
        if self.variant:
            fields['variant'] = self.variant
        if self.generation:
            fields['generation'] = self.generation
        if self.model_year:
            fields['year_of_manufacture'] = self.model_year
        if self.body_type:
            fields['body_type'] = self.body_type
        if self.doors:
            fields['doors'] = self.doors
        if self.seats:
            fields['seats'] = self.seats
        if self.fuel_type:
            fields['fuel_type'] = self.fuel_type
        if self.engine_displacement_cc:
            fields['engine_displacement_cc'] = self.engine_displacement_cc
        if self.engine_power_hp:
            fields['engine_power_hp'] = self.engine_power_hp
        if self.engine_power_kw:
            fields['engine_power_kw'] = self.engine_power_kw
        if self.transmission:
            fields['transmission'] = self.transmission
        if self.drive_type:
            fields['drive_type'] = self.drive_type
        if self.co2_emissions:
            fields['co2_emissions'] = self.co2_emissions
        if self.euro_standard:
            fields['euro_standard'] = self.euro_standard
        if self.gross_weight_kg:
            fields['max_weight_kg'] = self.gross_weight_kg
        if self.battery_capacity_kwh:
            fields['is_electric_vehicle'] = True
        if self.fuel_type in ('electric',):
            fields['is_electric_vehicle'] = True
        return fields


class BaseVINProvider(ABC):
    """Abstract base class for VIN decoder providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier string."""

    @abstractmethod
    def decode(self, vin: str) -> VehicleSpecs:
        """Decode VIN and return unified vehicle specs."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and has remaining quota."""

    @abstractmethod
    def get_remaining_quota(self) -> Optional[int]:
        """Return remaining API calls, or None if unlimited."""
