"""Maps provider API responses to unified VehicleSpecs dataclass.

CRITICAL: Output values must match autovitData.ts enum values exactly.
Vincario/NHTSA raw values are normalized to the frontend dropdown format.
"""
from .providers.base import VehicleSpecs

# ── Brand Normalization ──

_BRAND_ALIASES = {
    'VW': 'Volkswagen',
    'VOLKSWAGEN': 'Volkswagen',
    'MB': 'Mercedes-Benz',
    'MERCEDES-BENZ': 'Mercedes-Benz',
    'MERCEDES BENZ': 'Mercedes-Benz',
    'MERCEDES': 'Mercedes-Benz',
    'BMW': 'BMW',
    'LAND ROVER': 'Land Rover',
    'ROLLS-ROYCE': 'Rolls-Royce',
    'ROLLS ROYCE': 'Rolls-Royce',
    'ALFA ROMEO': 'Alfa Romeo',
    'ASTON MARTIN': 'Aston Martin',
    'MINI': 'MINI',
}


def normalize_brand(raw: str) -> str:
    """Normalize brand name to match autovitData AUTOVIT_BRANDS."""
    if not raw:
        return ''
    upper = raw.strip().upper()
    if upper in _BRAND_ALIASES:
        return _BRAND_ALIASES[upper]
    # Title case for unknown brands
    return raw.strip().title()


# ── Fuel Type Normalization ──
# Must output autovitData values: petrol, diesel, electric, hybrid,
# plugin-hybrid, petrol-lpg, petrol-cng, hydrogen

_FUEL_MAP = {
    'petrol': 'petrol',
    'gasoline': 'petrol',
    'benzina': 'petrol',
    'diesel': 'diesel',
    'electric': 'electric',
    'battery electric': 'electric',
    'bev': 'electric',
    'hybrid': 'hybrid',
    'mild hybrid': 'hybrid',
    'full hybrid': 'hybrid',
    'petrol / electric': 'plugin-hybrid',
    'plug-in hybrid': 'plugin-hybrid',
    'phev': 'plugin-hybrid',
    'plugin hybrid': 'plugin-hybrid',
    'plug-in hybrid electric vehicle (phev)': 'plugin-hybrid',
    'diesel / electric': 'hybrid',
    'lpg': 'petrol-lpg',
    'petrol / lpg': 'petrol-lpg',
    'cng': 'petrol-cng',
    'petrol / cng': 'petrol-cng',
    'natural gas': 'petrol-cng',
    'hydrogen': 'hydrogen',
    'fuel cell': 'hydrogen',
    'flex fuel': 'petrol',
    'compressed natural gas (cng)': 'petrol-cng',
    'liquefied petroleum gas (lpg)': 'petrol-lpg',
}


def normalize_fuel_type(raw: str) -> str:
    """Normalize fuel type to match autovitData AUTOVIT_FUEL_TYPES values."""
    if not raw:
        return ''
    key = raw.strip().lower()
    if key in _FUEL_MAP:
        return _FUEL_MAP[key]
    # Handle "X / Y" composite values from APIs
    for part in key.split('/'):
        part = part.strip()
        if part in _FUEL_MAP:
            return _FUEL_MAP[part]
    return key


# ── Body Type Normalization ──
# Must output autovitData values: sedan, suv, compact, combi, coupe,
# cabrio, minivan, city-car, small-car, pickup, van

_BODY_MAP = {
    'sedan': 'sedan',
    'saloon': 'sedan',
    'limousine': 'sedan',
    'suv': 'suv',
    'sport utility vehicle': 'suv',
    'crossover': 'suv',
    'suv / off-road': 'suv',
    'hatchback': 'compact',
    'compact': 'compact',
    'liftback': 'compact',
    'wagon': 'combi',
    'station wagon': 'combi',
    'estate': 'combi',
    'combi': 'combi',
    'break': 'combi',
    'touring': 'combi',
    'avant': 'combi',
    'coupe': 'coupe',
    'coupé': 'coupe',
    'convertible': 'cabrio',
    'cabriolet': 'cabrio',
    'cabrio': 'cabrio',
    'roadster': 'cabrio',
    'spider': 'cabrio',
    'spyder': 'cabrio',
    'minivan': 'minivan',
    'mpv': 'minivan',
    'van': 'van',
    'pickup': 'pickup',
    'truck': 'pickup',
    'pick-up': 'pickup',
    'city car': 'city-car',
    'microcar': 'city-car',
    'small car': 'small-car',
    'targa': 'cabrio',
    'fastback': 'compact',
    'gran coupe': 'coupe',
    'gran turismo': 'coupe',
    'sportback': 'compact',
}


def normalize_body_type(raw: str) -> str:
    """Normalize body type to match autovitData AUTOVIT_BODY_TYPES values."""
    if not raw:
        return ''
    key = raw.strip().lower()
    if key in _BODY_MAP:
        return _BODY_MAP[key]
    # NHTSA returns "Sedan/Saloon" — try each part
    for part in key.split('/'):
        part = part.strip()
        if part in _BODY_MAP:
            return _BODY_MAP[part]
    return key


# ── Transmission Normalization ──
# Must output autovitData values: manual, automatic, dual-clutch, cvt,
# semi-automatic, automated-manual

_TRANSMISSION_MAP = {
    'manual': 'manual',
    'automatic': 'automatic',
    'auto': 'automatic',
    'cvt': 'cvt',
    'continuously variable': 'cvt',
    'dsg': 'dual-clutch',
    'dct': 'dual-clutch',
    'pdk': 'dual-clutch',
    's tronic': 'dual-clutch',
    'dual clutch': 'dual-clutch',
    'double clutch': 'dual-clutch',
    'dual-clutch': 'dual-clutch',
    'semi-automatic': 'semi-automatic',
    'semi automatic': 'semi-automatic',
    'automated manual': 'automated-manual',
    'automated-manual': 'automated-manual',
    'amt': 'automated-manual',
    'tiptronic': 'automatic',
    'steptronic': 'automatic',
    'multitronic': 'cvt',
    'powershift': 'dual-clutch',
    'e-cvt': 'cvt',
}


def normalize_transmission(raw: str) -> str:
    """Normalize transmission to match autovitData AUTOVIT_GEARBOX_TYPES values."""
    if not raw:
        return ''
    key = raw.strip().lower()
    if key in _TRANSMISSION_MAP:
        return _TRANSMISSION_MAP[key]
    for part in key.split('/'):
        part = part.strip()
        if part in _TRANSMISSION_MAP:
            return _TRANSMISSION_MAP[part]
    return key


# ── Drive Type Normalization ──
# Must output autovitData values: front-wheel, rear-wheel,
# all-wheel-permanent, all-wheel-auto, all-wheel-lock

_DRIVE_MAP = {
    'fwd': 'front-wheel',
    'front wheel drive': 'front-wheel',
    'front-wheel drive': 'front-wheel',
    'ff': 'front-wheel',
    'rwd': 'rear-wheel',
    'rear wheel drive': 'rear-wheel',
    'rear-wheel drive': 'rear-wheel',
    'fr': 'rear-wheel',
    'awd': 'all-wheel-permanent',
    'all wheel drive': 'all-wheel-permanent',
    'all-wheel drive': 'all-wheel-permanent',
    '4wd': 'all-wheel-lock',
    '4x4': 'all-wheel-lock',
    'four wheel drive': 'all-wheel-lock',
    '4matic': 'all-wheel-permanent',
    'xdrive': 'all-wheel-permanent',
    'quattro': 'all-wheel-permanent',
    '4motion': 'all-wheel-permanent',
}


def normalize_drive_type(raw: str) -> str:
    """Normalize drive type to match autovitData AUTOVIT_DRIVE_TYPES values."""
    if not raw:
        return ''
    key = raw.strip().lower()
    if key in _DRIVE_MAP:
        return _DRIVE_MAP[key]
    # NHTSA returns "AWD/All-Wheel Drive" — try each part
    for part in key.split('/'):
        part = part.strip()
        if part in _DRIVE_MAP:
            return _DRIVE_MAP[part]
    return key


# ── Euro Standard Normalization ──
# Must output autovitData values: euro-6d, euro-6d-temp, euro-6, euro-5, etc.

_EURO_MAP = {
    'euro 6d': 'euro-6d',
    'euro 6d-temp': 'euro-6d-temp',
    'euro 6': 'euro-6',
    'euro 5': 'euro-5',
    'euro 4': 'euro-4',
    'euro 3': 'euro-3',
    'euro 2': 'euro-2',
    'euro 1': 'euro-1',
    'euro6d': 'euro-6d',
    'euro6': 'euro-6',
    'euro5': 'euro-5',
    'euro4': 'euro-4',
}


def normalize_euro_standard(raw: str) -> str:
    """Normalize euro emission standard."""
    if not raw:
        return ''
    key = raw.strip().lower()
    return _EURO_MAP.get(key, key)


# ── Unit Conversions ──

def hp_to_kw(hp: int) -> int:
    """Convert horsepower to kilowatts."""
    if not hp:
        return 0
    return round(hp * 0.7457)


def kw_to_hp(kw: int) -> int:
    """Convert kilowatts to horsepower."""
    if not kw:
        return 0
    return round(kw / 0.7457)


# ── Safe Parsers ──

def safe_int(val) -> int:
    """Parse int from string/float safely, returns 0 on failure."""
    if val is None:
        return 0
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return 0


def safe_float(val) -> float:
    """Parse float from string safely, returns 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return 0.0


# ── Vincario Mapper ──

def map_vincario_response(raw_data: dict, vin: str = '') -> VehicleSpecs:
    """Map Vincario API response to VehicleSpecs.

    Args:
        raw_data: The JSON response from Vincario decode endpoint.
        vin: The original VIN that was decoded.
    """
    specs = VehicleSpecs(
        provider='vincario',
        raw_response=raw_data,
        vin=vin,
    )

    specs.brand = normalize_brand(raw_data.get('Make', ''))
    specs.model = raw_data.get('Model', '') or ''
    specs.model_year = safe_int(raw_data.get('Model Year'))
    specs.body_type = normalize_body_type(raw_data.get('Body', ''))
    specs.seats = safe_int(raw_data.get('Number of Seats'))
    specs.doors = safe_int(raw_data.get('Number of Doors'))
    specs.engine_displacement_cc = safe_int(
        raw_data.get('Engine Displacement (ccm)')
    )
    specs.fuel_type = normalize_fuel_type(
        raw_data.get('Fuel Type - Primary', '')
    )
    specs.gears = safe_int(raw_data.get('Number of Gears'))
    specs.euro_standard = normalize_euro_standard(
        raw_data.get('Emission Standard', '')
    )
    specs.co2_emissions = safe_int(
        raw_data.get('Average CO2 Emission (g/km)')
    )
    specs.max_speed_kmh = safe_int(raw_data.get('Max Speed (km/h)'))
    specs.curb_weight_kg = safe_int(raw_data.get('Weight Empty (kg)'))
    specs.gross_weight_kg = safe_int(raw_data.get('Max Weight (kg)'))
    specs.length_mm = safe_int(raw_data.get('Length (mm)'))
    specs.width_mm = safe_int(raw_data.get('Width (mm)'))
    specs.height_mm = safe_int(raw_data.get('Height (mm)'))
    specs.wheelbase_mm = safe_int(raw_data.get('Wheelbase (mm)'))
    specs.manufacturer = raw_data.get('Manufacturer', '') or ''
    specs.plant_country = raw_data.get('Plant Country', '') or ''

    # Engine code: prefer technical 'Engine Code' over descriptive 'Engine Type'
    specs.engine_code = (
        raw_data.get('Engine Code', '') or
        raw_data.get('Engine Type', '') or ''
    )

    # Variant: use 'Vehicle Specification' if available
    specs.variant = raw_data.get('Vehicle Specification', '') or ''

    # Vincario doesn't always return transmission/drive directly
    # Try to infer from Vehicle Specification string
    vehicle_spec = (raw_data.get('Vehicle Specification', '') or '').lower()
    if not specs.transmission:
        if 'automatic' in vehicle_spec or 'auto' in vehicle_spec:
            specs.transmission = 'automatic'
        elif 'manual' in vehicle_spec:
            specs.transmission = 'manual'
        elif 'dsg' in vehicle_spec or 'dct' in vehicle_spec:
            specs.transmission = 'dual-clutch'
        elif 'cvt' in vehicle_spec:
            specs.transmission = 'cvt'

    if not specs.drive_type:
        if '4matic' in vehicle_spec:
            specs.drive_type = 'all-wheel-permanent'
        elif 'xdrive' in vehicle_spec:
            specs.drive_type = 'all-wheel-permanent'
        elif 'quattro' in vehicle_spec:
            specs.drive_type = 'all-wheel-permanent'
        elif '4motion' in vehicle_spec:
            specs.drive_type = 'all-wheel-permanent'
        elif '4x4' in vehicle_spec or '4wd' in vehicle_spec:
            specs.drive_type = 'all-wheel-lock'
        elif 'awd' in vehicle_spec:
            specs.drive_type = 'all-wheel-permanent'

    # Calculate confidence
    specs.confidence_score = _calculate_confidence(specs)

    return specs


# ── NHTSA Mapper ──

_NHTSA_FIELD_MAP = {
    'Make': 'brand',
    'Model': 'model',
    'Model Year': 'model_year',
    'Body Class': 'body_type',
    'Doors': 'doors',
    'Displacement (CC)': 'engine_displacement_cc',
    'Engine Number of Cylinders': 'cylinders',
    'Fuel Type - Primary': 'fuel_type',
    'Transmission Style': 'transmission',
    'Drive Type': 'drive_type',
    'Engine Brake (hp) From': 'engine_power_hp',
    'Manufacturer Name': 'manufacturer',
    'Plant Country': 'plant_country',
    'Plant City': 'plant_city',
    'Series': 'variant',
    'Trim': 'trim',
}


def map_nhtsa_response(results: list, vin: str = '') -> VehicleSpecs:
    """Map NHTSA vPIC API Results array to VehicleSpecs.

    Args:
        results: The 'Results' array from NHTSA decode response.
        vin: The original VIN that was decoded.
    """
    # Build lookup from Results array
    lookup = {}
    for item in results:
        variable = item.get('Variable', '')
        value = item.get('Value')
        if variable and value and str(value).strip():
            lookup[variable] = str(value).strip()

    specs = VehicleSpecs(
        provider='nhtsa',
        raw_response={'Results': results},
        vin=vin,
    )

    specs.brand = normalize_brand(lookup.get('Make', ''))
    specs.model = lookup.get('Model', '')
    specs.model_year = safe_int(lookup.get('Model Year'))
    specs.body_type = normalize_body_type(lookup.get('Body Class', ''))
    specs.doors = safe_int(lookup.get('Doors'))
    specs.engine_displacement_cc = safe_int(lookup.get('Displacement (CC)'))
    specs.cylinders = safe_int(lookup.get('Engine Number of Cylinders'))
    specs.fuel_type = normalize_fuel_type(
        lookup.get('Fuel Type - Primary', '')
    )
    specs.transmission = normalize_transmission(
        lookup.get('Transmission Style', '')
    )
    specs.drive_type = normalize_drive_type(lookup.get('Drive Type', ''))
    specs.engine_power_hp = safe_int(
        lookup.get('Engine Brake (hp) From')
    )
    specs.manufacturer = lookup.get('Manufacturer Name', '')
    specs.plant_country = lookup.get('Plant Country', '')
    specs.plant_city = lookup.get('Plant City', '')

    # Variant: combine Series + Trim
    series = lookup.get('Series', '')
    trim = lookup.get('Trim', '')
    if series and trim:
        specs.variant = f"{series} {trim}"
    elif series:
        specs.variant = series
    elif trim:
        specs.variant = trim

    # Convert HP to kW if HP available
    if specs.engine_power_hp:
        specs.engine_power_kw = hp_to_kw(specs.engine_power_hp)

    # Calculate confidence
    specs.confidence_score = _calculate_confidence(specs)

    return specs


# ── Confidence Score ──

# Fields that count toward confidence
_CONFIDENCE_FIELDS = [
    'brand', 'model', 'model_year', 'body_type', 'doors', 'seats',
    'fuel_type', 'engine_displacement_cc', 'engine_power_hp',
    'transmission', 'drive_type', 'co2_emissions', 'euro_standard',
    'manufacturer', 'plant_country', 'curb_weight_kg',
]


def _calculate_confidence(specs: VehicleSpecs) -> float:
    """Calculate confidence score based on populated fields."""
    total = len(_CONFIDENCE_FIELDS)
    decoded = 0
    for field_name in _CONFIDENCE_FIELDS:
        val = getattr(specs, field_name, None)
        if val and val != 0 and val != 0.0:
            decoded += 1
    specs.fields_decoded = decoded
    specs.fields_total = total
    return round(decoded / total, 2) if total else 0.0
