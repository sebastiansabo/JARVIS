# Claude Code Prompt: Build VIN Decoder Connector for JARVIS CarPark Module

## CONTEXT

You are building a VIN (Vehicle Identification Number) decoder connector for JARVIS — a Flask + React enterprise platform. This connector lives inside the CarPark module and auto-populates vehicle specifications when a user enters a VIN.

JARVIS uses:
- **Backend:** Flask (Python 3.11), PostgreSQL 18.1, psycopg2 connection pooling, layered architecture (Routes → Services → Repositories → DB)
- **Frontend:** React 19 + TypeScript 5.8, Vite, shadcn/ui, TanStack React Query, Zustand, Tailwind CSS
- **HTTP Client:** `requests` library with `HTTPAdapter` + `urllib3.util.retry.Retry` for resilience
- **Auth:** Flask-Login session-based + RBAC
- **Config:** Environment variables loaded via dataclass pattern
- **Deployment:** Docker on DigitalOcean, Gunicorn with 3 workers

## EXISTING CONNECTOR PATTERNS TO FOLLOW

JARVIS has two production connectors you MUST mirror exactly:

### Exception Hierarchy Pattern
```python
# File: jarvis/carpark/connectors/vin_decoder/exceptions.py

class VINDecoderError(Exception):
    """Base exception for all VIN decoder errors."""
    def __init__(self, message, code=None, details=None, is_retryable=False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.is_retryable = is_retryable

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message

class AuthenticationError(VINDecoderError):
    """Invalid API key or unauthorized."""
    def __init__(self, message='Authentication failed', **kwargs):
        super().__init__(message, code='AUTH_ERROR', is_retryable=False, **kwargs)

class RateLimitError(VINDecoderError):
    """API quota exceeded."""
    def __init__(self, message='Rate limit exceeded', retry_after=None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, code='RATE_LIMIT', is_retryable=True, details={'retry_after': retry_after, **(kwargs.get('details', {}))}, **{k: v for k, v in kwargs.items() if k != 'details'})

class QuotaExhaustedError(RateLimitError):
    """Monthly/daily API quota fully consumed."""
    def __init__(self, message='API quota exhausted', remaining=0, **kwargs):
        super().__init__(message, **kwargs)
        self.remaining = remaining

class VINNotFoundError(VINDecoderError):
    """VIN not found in provider database."""
    def __init__(self, vin, **kwargs):
        super().__init__(f'VIN not found: {vin}', code='VIN_NOT_FOUND', is_retryable=False, details={'vin': vin}, **kwargs)

class VINValidationError(VINDecoderError):
    """VIN format invalid (not 17 chars, bad check digit, etc.)."""
    def __init__(self, vin, reason='Invalid VIN format', **kwargs):
        super().__init__(reason, code='VIN_INVALID', is_retryable=False, details={'vin': vin, 'reason': reason}, **kwargs)

class NetworkError(VINDecoderError):
    """Connection failure."""
    def __init__(self, message='Network error', original_error=None, **kwargs):
        super().__init__(message, code='NETWORK_ERROR', is_retryable=True, details={'original_error': str(original_error) if original_error else None}, **kwargs)

class TimeoutError(NetworkError):
    """Request timed out."""
    def __init__(self, message='Request timed out', timeout_seconds=None, **kwargs):
        super().__init__(message, **kwargs)
        self.code = 'TIMEOUT'

class APIError(VINDecoderError):
    """Non-success HTTP response."""
    def __init__(self, message, status_code, response_body=None, **kwargs):
        self.status_code = status_code
        self.response_body = response_body
        is_retryable = status_code in (500, 502, 503, 504)
        super().__init__(message, code=f'API_ERROR_{status_code}', is_retryable=is_retryable, **kwargs)

class ParseError(VINDecoderError):
    """Failed to parse API response."""
    def __init__(self, message='Failed to parse response', **kwargs):
        super().__init__(message, code='PARSE_ERROR', is_retryable=False, **kwargs)

class ProviderUnavailableError(VINDecoderError):
    """All providers failed."""
    def __init__(self, providers_tried, errors, **kwargs):
        msg = f"All VIN providers failed: {', '.join(providers_tried)}"
        super().__init__(msg, code='ALL_PROVIDERS_FAILED', is_retryable=False, details={'providers': providers_tried, 'errors': [str(e) for e in errors]}, **kwargs)
```

### Config Pattern
```python
# File: jarvis/carpark/connectors/vin_decoder/config.py
from dataclasses import dataclass
import os

@dataclass
class VINDecoderConfig:
    """VIN Decoder connector configuration."""

    # Provider priority (first = primary, rest = fallback)
    PROVIDER_PRIORITY: list = None  # ['vincario', 'nhtsa']

    # Vincario API (primary — European coverage)
    # Auth: SHA1-based control sum, NOT SHA256
    # Control sum = sha1(f"{VIN}|{ID}|{API_KEY}|{SECRET_KEY}").hexdigest()[:10]
    VINCARIO_API_KEY: str = ''
    VINCARIO_SECRET_KEY: str = ''
    VINCARIO_BASE_URL: str = 'https://api.vincario.com/3.2'

    # NHTSA vPIC API (fallback — free, US-focused but decodes WMI globally)
    NHTSA_BASE_URL: str = 'https://vpic.nhtsa.dot.gov/api/vehicles'

    # Request settings
    REQUEST_TIMEOUT: int = 15           # seconds
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0       # seconds (exponential backoff)

    # Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_DAYS: int = 90            # Cache VIN results for 90 days (specs don't change)

    # Rate limiting
    VINCARIO_MAX_REQUESTS_PER_MONTH: int = 500   # Based on subscription plan
    VINCARIO_RATE_LIMIT_BUFFER: int = 10

    def __post_init__(self):
        if self.PROVIDER_PRIORITY is None:
            self.PROVIDER_PRIORITY = ['vincario', 'nhtsa']

    @classmethod
    def from_env(cls) -> 'VINDecoderConfig':
        return cls(
            PROVIDER_PRIORITY=os.environ.get('VIN_PROVIDER_PRIORITY', 'vincario,nhtsa').split(','),
            VINCARIO_API_KEY=os.environ.get('VINCARIO_API_KEY', ''),
            VINCARIO_SECRET_KEY=os.environ.get('VINCARIO_SECRET_KEY', ''),
            VINCARIO_BASE_URL=os.environ.get('VINCARIO_BASE_URL', 'https://api.vincario.com/3.2'),
            NHTSA_BASE_URL=os.environ.get('NHTSA_BASE_URL', 'https://vpic.nhtsa.dot.gov/api/vehicles'),
            REQUEST_TIMEOUT=int(os.environ.get('VIN_REQUEST_TIMEOUT', '15')),
            MAX_RETRIES=int(os.environ.get('VIN_MAX_RETRIES', '3')),
            CACHE_ENABLED=os.environ.get('VIN_CACHE_ENABLED', 'true').lower() == 'true',
            CACHE_TTL_DAYS=int(os.environ.get('VIN_CACHE_TTL_DAYS', '90')),
            VINCARIO_MAX_REQUESTS_PER_MONTH=int(os.environ.get('VINCARIO_MAX_REQUESTS', '500')),
        )

DEFAULT_CONFIG = VINDecoderConfig()
```

### HTTP Client Pattern
```python
# File: jarvis/carpark/connectors/vin_decoder/client.py

import hashlib
import hmac
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import VINDecoderConfig, DEFAULT_CONFIG
from .exceptions import *

logger = logging.getLogger('jarvis.carpark.connectors.vin_decoder')


class VINDecoderClient:
    """
    Multi-provider VIN decoder client with automatic failover.

    Provider chain: Vincario (primary, EU coverage) → NHTSA (fallback, free).
    Results cached in DB to avoid redundant API calls.
    """

    def __init__(self, config: VINDecoderConfig = None):
        self.config = config or DEFAULT_CONFIG
        self._session = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            retry_strategy = Retry(
                total=self.config.MAX_RETRIES,
                backoff_factor=self.config.RETRY_BASE_DELAY,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=['GET', 'POST'],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self._session.mount('https://', adapter)
            self._session.mount('http://', adapter)
            self._session.headers.update({
                'Accept': 'application/json',
                'User-Agent': 'JARVIS-CarPark-VINDecoder/1.0',
            })
        return self._session

    # ... implement decode methods per provider
```

## YOUR TASK

Build the complete VIN decoder connector for JARVIS CarPark. This includes ALL of the following files:

### FILE STRUCTURE TO CREATE

```
jarvis/carpark/connectors/
├── __init__.py
└── vin_decoder/
    ├── __init__.py
    ├── config.py                    # VINDecoderConfig dataclass (from_env)
    ├── exceptions.py                # Full exception hierarchy
    ├── client.py                    # VINDecoderClient — multi-provider with failover
    ├── providers/
    │   ├── __init__.py
    │   ├── base.py                  # Abstract base provider class
    │   ├── vincario_provider.py     # Vincario API implementation
    │   └── nhtsa_provider.py        # NHTSA vPIC API implementation
    ├── mapper.py                    # Maps provider responses → unified VehicleSpecs dataclass
    ├── validator.py                 # VIN format validation (ISO 3779, check digit)
    └── cache.py                     # DB-backed cache using BaseRepository
```

### REQUIREMENTS

#### 1. VIN Validation (`validator.py`)
- Validate 17-character length
- Validate allowed characters (A-Z, 0-9, excluding I, O, Q)
- Calculate and verify ISO 3779 check digit (position 9)
- Extract WMI (positions 1-3) for manufacturer identification
- Extract VDS (positions 4-8) for vehicle descriptor
- Extract VIS (positions 10-17) for vehicle identifier
- Return structured validation result with breakdown

#### 2. Abstract Provider (`providers/base.py`)
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class VehicleSpecs:
    """Unified vehicle specification result from any VIN decoder provider."""
    # Source
    provider: str                          # 'vincario', 'nhtsa'
    raw_response: Dict[str, Any] = field(default_factory=dict, repr=False)
    decoded_at: datetime = field(default_factory=datetime.utcnow)

    # Identity
    vin: str = ''
    brand: str = ''                        # Make (Volvo, VW, Audi, etc.)
    model: str = ''                        # Model (XC40, Passat, Q7, etc.)
    variant: str = ''                      # Trim/version
    generation: str = ''
    model_year: int = 0
    manufacture_year: int = 0

    # Body
    body_type: str = ''                    # sedan, suv, hatchback, wagon, coupe, van, pickup
    doors: int = 0
    seats: int = 0
    color: str = ''

    # Engine
    fuel_type: str = ''                    # petrol, diesel, hybrid, plugin_hybrid, electric, lpg
    engine_displacement_cc: int = 0
    engine_power_hp: int = 0
    engine_power_kw: int = 0
    engine_code: str = ''
    cylinders: int = 0

    # Transmission
    transmission: str = ''                 # manual, automatic
    transmission_detail: str = ''          # DSG, CVT, Tiptronic, etc.
    drive_type: str = ''                   # FWD, RWD, AWD, 4WD
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
    fuel_consumption_combined: float = 0.0   # l/100km or kWh/100km
    fuel_tank_capacity: float = 0.0          # liters
    co2_emissions: int = 0                   # g/km
    euro_standard: str = ''                  # Euro 6d, etc.
    battery_capacity_kwh: float = 0.0        # For EVs/PHEVs

    # Manufacturing
    manufacturer: str = ''                   # Full manufacturer name
    plant_country: str = ''
    plant_city: str = ''
    produced_from: str = ''                  # Production start year
    produced_to: str = ''                    # Production end year or 'present'

    # Equipment (if available from provider)
    equipment: List[str] = field(default_factory=list)
    standard_equipment: List[str] = field(default_factory=list)
    optional_equipment: List[str] = field(default_factory=list)

    # Confidence
    confidence_score: float = 0.0            # 0.0-1.0 how complete the decode was
    fields_decoded: int = 0
    fields_total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        from dataclasses import asdict
        d = asdict(self)
        d['decoded_at'] = self.decoded_at.isoformat()
        d.pop('raw_response', None)
        return d

    def to_vehicle_fields(self) -> Dict[str, Any]:
        """Map to carpark_vehicles table columns for auto-population."""
        fields = {}
        if self.brand: fields['brand'] = self.brand
        if self.model: fields['model'] = self.model
        if self.variant: fields['variant'] = self.variant
        if self.generation: fields['generation'] = self.generation
        if self.model_year: fields['year_of_manufacture'] = self.model_year
        if self.body_type: fields['body_type'] = self.body_type
        if self.doors: fields['doors'] = self.doors
        if self.seats: fields['seats'] = self.seats
        if self.fuel_type: fields['fuel_type'] = self.fuel_type
        if self.engine_displacement_cc: fields['engine_displacement_cc'] = self.engine_displacement_cc
        if self.engine_power_hp: fields['engine_power_hp'] = self.engine_power_hp
        if self.engine_power_kw: fields['engine_power_kw'] = self.engine_power_kw
        if self.transmission: fields['transmission'] = self.transmission
        if self.drive_type: fields['drive_type'] = self.drive_type
        if self.co2_emissions: fields['co2_emissions'] = self.co2_emissions
        if self.euro_standard: fields['euro_standard'] = self.euro_standard
        if self.battery_capacity_kwh: fields['is_electric_vehicle'] = True
        return fields


class BaseVINProvider(ABC):
    """Abstract base class for VIN decoder providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier string."""
        pass

    @abstractmethod
    def decode(self, vin: str) -> VehicleSpecs:
        """Decode VIN and return unified specs."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and has remaining quota."""
        pass

    @abstractmethod
    def get_remaining_quota(self) -> Optional[int]:
        """Return remaining API calls, or None if unlimited."""
        pass
```

#### 3. Vincario Provider (`providers/vincario_provider.py`)

**VERIFIED API SPECIFICATION (from official docs v3.2):**

**Base URL:** `https://api.vincario.com/3.2/`

**Authentication — Control Sum Calculation:**
The control sum is the first 10 characters of a SHA1 hash (NOT SHA256). The input string depends on whether the call includes a VIN:
- With VIN: `sha1(f"{VIN}|{ID}|{API_KEY}|{SECRET_KEY}").hexdigest()[:10]` — VIN must be UPPERCASE
- Without VIN: `sha1(f"{ID}|{API_KEY}|{SECRET_KEY}").hexdigest()[:10]`

Where `ID` is the action string: `decode`, `info`, `stolen-check`, `vehicle-market-value`, `oem`, `balance`

**Python reference implementation:**
```python
import hashlib

def _control_sum(self, vin: str = None, action_id: str = 'decode') -> str:
    """Calculate Vincario API control sum (first 10 chars of SHA1)."""
    if vin:
        raw = f"{vin.upper()}|{action_id}|{self.api_key}|{self.secret_key}"
    else:
        raw = f"{action_id}|{self.api_key}|{self.secret_key}"
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]
```

**Endpoints:**

| Action | ID string | URL Pattern | Has VIN |
|--------|-----------|-------------|---------|
| VIN Decode | `decode` | `GET /{api_key}/{control_sum}/decode/{VIN}.json` | Yes |
| VIN Decode Info | `info` | `GET /{api_key}/{control_sum}/info/{VIN}.json` | Yes |
| Stolen Check | `stolen-check` | `GET /{api_key}/{control_sum}/stolen-check/{VIN}.json` | Yes |
| Market Value | `vehicle-market-value` | `GET /{api_key}/{control_sum}/vehicle-market-value/{VIN}.json` | Yes |
| OEM Lookup | `oem` | `GET /{api_key}/{control_sum}/oem/{VIN}.json` | Yes |
| Get Balance | `balance` | `GET /{api_key}/{control_sum}/balance.json` | No |

**Full decode request example:**
```python
vin = "YV1XZ98AWN1234567"
action_id = "decode"
control = hashlib.sha1(f"{vin}|{action_id}|{api_key}|{secret_key}".encode()).hexdigest()[:10]
url = f"https://api.vincario.com/3.2/{api_key}/{control}/decode/{vin}.json"
response = requests.get(url, timeout=15)
```

**Response fields (50+ attributes, EU market average ~40 populated):**

```
Make                              # e.g., "Volvo"
Manufacturer                      # e.g., "Volvo Car Corporation"
Plant Country                     # e.g., "Belgium"
Manufacturer Address              # Full manufacturer address
Model                             # e.g., "XC40"
Model Year                        # e.g., 2024
Product Type                      # e.g., "Passenger Car"
Body                              # e.g., "SUV", "Sedan", "Hatchback"
Number of Seats                   # e.g., 5
Number of Doors                   # e.g., 5
Engine Type                       # e.g., "Electric"
Engine Manufacturer               # e.g., "Volvo"
Engine Code                       # e.g., "XE_REEV_P6_BEV"
Engine Displacement (ccm)         # e.g., 1969
Fuel Type - Primary               # e.g., "Diesel", "Electric", "Petrol"
Number of Gears                   # e.g., 8
Emission Standard                 # e.g., "Euro 6d"
Average CO2 Emission (g/km)       # e.g., 0 (for EV)
Max Speed (km/h)                  # e.g., 160
Weight Empty (kg)                 # e.g., 2055
Max Weight (kg)                   # e.g., 2550
Length (mm)                       # e.g., 4425
Width (mm)                        # e.g., 1863
Height (mm)                       # e.g., 1652
Wheelbase (mm)                    # e.g., 2702
Wheel Size                        # e.g., "235/50 R19"
Track Front (mm)                  # Track width front axle
Track Rear (mm)                   # Track width rear axle
Number of Axles                   # e.g., 2
Number Wheels                     # e.g., 4
Brake System                      # e.g., "Hydraulic"
Front Brakes                      # e.g., "Ventilated Discs"
ABS                               # e.g., "Yes"
Suspension                        # e.g., "Independent"
Front Suspension                  # e.g., "McPherson"
Maximum Trunk Capacity            # e.g., 1290 liters
Max roof load (kg)                # e.g., 75
Permitted trailer load without brakes (kg)  # e.g., 750
Check Digit                       # VIN check digit
Sequential Number                 # Production sequence
Vehicle Specification             # Full spec string
Make ID                           # Internal Vincario make ID
Model ID                          # Internal Vincario model ID
Product Type ID                   # Internal product type ID
Vehicle ID                        # Internal vehicle ID
Body ID                           # Internal body type ID
Fuel Type - Primary ID            # Internal fuel type ID
```

**IMPORTANT: The `info` endpoint returns the LIST of fields available for a given VIN (free of charge, doesn't consume balance). Call `info` first to check field availability, then call `decode` to get actual values.**

**Balance response format:**
```json
{
  "API Decode": 478,
  "API Stolen Check": 100,
  "API Vehicle Market Value": 50
}
```

**Credentials (store in environment variables, NEVER hardcode):**
```bash
VINCARIO_API_KEY=2ce2ba1b881d
VINCARIO_SECRET_KEY=7bc47b0b00
```

Implement:
- `decode(vin)` → calls API, maps response via `mapper.py` to `VehicleSpecs`
- `info(vin)` → free call to check which fields are available before consuming a decode credit
- `is_available()` → checks API key exists + remaining quota > buffer
- `get_remaining_quota()` → calls balance endpoint, returns `API Decode` count
- Hash payload for logging (never log raw API keys or secret keys)
- Handle all HTTP status codes (200, 400, 401, 402, 403, 404, 429, 5xx)
- Exponential backoff on retries
- VIN must be sent UPPERCASE
- Control sum uses SHA1 (not SHA256)

#### 4. NHTSA Provider (`providers/nhtsa_provider.py`)

API details:
- **Base URL:** `https://vpic.nhtsa.dot.gov/api/vehicles`
- **Auth:** None (free, public, no registration)
- **Decode endpoint:** `GET /decodevin/{vin}?format=json`
- **Response:** JSON with `Results` array of `{Variable, Value, ValueId, VariableId}` key-value pairs
- **Key fields:** Make, Model, ModelYear, BodyClass, DisplacementCC, EngineHP, EngineCylinders, FuelTypePrimary, TransmissionStyle, DriveType, Doors, GVWR, PlantCountry, PlantCity, ErrorCode, ErrorText
- **Limitations:** US-focused, less detail on EU-specific trims and equipment, no equipment lists

Implement:
- `decode(vin)` → calls API, maps response via `mapper.py` to `VehicleSpecs`
- `is_available()` → always True (free, unlimited)
- `get_remaining_quota()` → returns None (unlimited)
- Parse the key-value pair array format into structured data
- Handle `ErrorCode` != '0' in individual result items

#### 5. Mapper (`mapper.py`)

**Vincario field name → VehicleSpecs mapping (use these EXACT Vincario field names as dict keys):**

```python
VINCARIO_FIELD_MAP = {
    # Vincario response key              → VehicleSpecs attribute
    'Make':                               'brand',
    'Model':                              'model',
    'Model Year':                         'model_year',
    'Body':                               'body_type',
    'Number of Seats':                    'seats',
    'Number of Doors':                    'doors',
    'Engine Type':                        'engine_code',          # map to engine_code (descriptive)
    'Engine Code':                        'engine_code',          # override if present (technical code)
    'Engine Displacement (ccm)':          'engine_displacement_cc',
    'Fuel Type - Primary':                'fuel_type',
    'Number of Gears':                    'gears',
    'Emission Standard':                  'euro_standard',
    'Average CO2 Emission (g/km)':        'co2_emissions',
    'Max Speed (km/h)':                   'max_speed_kmh',
    'Weight Empty (kg)':                  'curb_weight_kg',
    'Max Weight (kg)':                    'gross_weight_kg',
    'Length (mm)':                        'length_mm',
    'Width (mm)':                         'width_mm',
    'Height (mm)':                        'height_mm',
    'Wheelbase (mm)':                     'wheelbase_mm',
    'Wheel Size':                         None,                   # store in raw_response
    'Track Front (mm)':                   None,
    'Track Rear (mm)':                    None,
    'Manufacturer':                       'manufacturer',
    'Plant Country':                      'plant_country',
    'Product Type':                       None,                   # "Passenger Car", "Truck", etc.
    'Vehicle Specification':              'variant',              # often contains trim/variant info
    'Brake System':                       None,
    'Front Brakes':                       None,
    'ABS':                                None,
    'Suspension':                         None,
    'Front Suspension':                   None,
    'Maximum Trunk Capacity':             None,
    'Max roof load (kg)':                 None,
    'Engine Manufacturer':                None,
    'Manufacturer Address':               None,
}
```

**NHTSA vPIC field name → VehicleSpecs mapping (Results array key-value pairs, use `Variable` field):**

```python
NHTSA_FIELD_MAP = {
    'Make':                               'brand',
    'Model':                              'model',
    'Model Year':                         'model_year',
    'Body Class':                         'body_type',
    'Doors':                              'doors',
    'Displacement (CC)':                  'engine_displacement_cc',
    'Displacement (L)':                   None,                   # prefer CC
    'Engine Number of Cylinders':         'cylinders',
    'Fuel Type - Primary':                'fuel_type',
    'Transmission Style':                 'transmission',
    'Drive Type':                         'drive_type',
    'Engine Brake (hp) From':             'engine_power_hp',
    'Manufacturer Name':                  'manufacturer',
    'Plant Country':                      'plant_country',
    'Plant City':                         'plant_city',
    'Series':                             'variant',
    'Trim':                               'variant',             # append to variant if Series exists
    'GVWR':                               'gross_weight_kg',
}
```

Normalize data from each provider into consistent formats:
- Brand names: uppercase first letter, handle aliases (VW → Volkswagen, MB → Mercedes-Benz)
- Fuel types: normalize to enum (petrol, diesel, hybrid, plugin_hybrid, electric, lpg, cng). Vincario uses "Diesel", "Electric", "Petrol", "Petrol / Electric" etc.
- Body types: normalize to enum (sedan, suv, hatchback, wagon, coupe, convertible, van, pickup, minivan). Vincario uses "SUV", "Sedan", "Hatchback" etc.
- Transmission: normalize to (manual, automatic). Vincario doesn't always return this directly — infer from `Number of Gears` and `Vehicle Specification`
- Drive type: normalize to (FWD, RWD, AWD, 4WD). Vincario doesn't always return this directly — parse from `Vehicle Specification` if present
- Handle unit conversions (HP ↔ kW: kW = HP × 0.7457). Note: Vincario does NOT return HP/kW directly — you may need to parse from Vehicle Specification or leave empty
- Calculate confidence_score: count non-empty mapped fields / total mappable fields

#### 6. Cache (`cache.py`)

DB-backed cache using BaseRepository pattern:

```sql
CREATE TABLE IF NOT EXISTS carpark_vin_cache (
    id SERIAL PRIMARY KEY,
    vin VARCHAR(17) NOT NULL,
    provider VARCHAR(30) NOT NULL,
    specs_json JSONB NOT NULL,
    confidence_score DECIMAL(3,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    UNIQUE(vin, provider)
);
CREATE INDEX IF NOT EXISTS idx_vin_cache_vin ON carpark_vin_cache(vin);
CREATE INDEX IF NOT EXISTS idx_vin_cache_expires ON carpark_vin_cache(expires_at);
```

- Check cache before calling any provider
- Store successful results with TTL (default 90 days — vehicle specs don't change)
- Return cached result with `provider: 'cache'` marker
- Cleanup expired entries (add to scheduled tasks)

#### 7. Client (`client.py`) — Main Entry Point

The `VINDecoderClient` is the ONLY class that routes/services interact with:

```python
class VINDecoderClient:
    def decode(self, vin: str, skip_cache: bool = False) -> VehicleSpecs:
        """
        Decode VIN through provider chain with caching.

        1. Validate VIN format
        2. Check cache (unless skip_cache=True)
        3. Try providers in priority order (vincario → nhtsa)
        4. First successful result: cache it, return it
        5. All failed: raise ProviderUnavailableError with all errors
        """

    def validate(self, vin: str) -> dict:
        """
        Validate VIN format without decoding.
        Returns: {valid: bool, vin: str, wmi: str, vds: str, vis: str, errors: []}
        """

    def get_provider_status(self) -> list:
        """
        Return status of all configured providers.
        Returns: [{name, available, remaining_quota, last_error}]
        """
```

### ROUTES TO ADD

Add these endpoints to `jarvis/carpark/routes.py`:

```python
# VIN Decoder
@carpark_bp.route('/api/carpark/vin/decode/<vin>', methods=['GET'])
@login_required
def decode_vin(vin):
    """Decode VIN and return vehicle specs."""
    skip_cache = request.args.get('refresh', 'false').lower() == 'true'
    try:
        specs = _vin_client.decode(vin, skip_cache=skip_cache)
        return jsonify({
            'success': True,
            'data': {
                'specs': specs.to_dict(),
                'vehicle_fields': specs.to_vehicle_fields(),
                'provider': specs.provider,
                'confidence': specs.confidence_score,
            }
        })
    except VINValidationError as e:
        return jsonify({'success': False, 'error': str(e), 'code': e.code}), 400
    except VINNotFoundError as e:
        return jsonify({'success': False, 'error': str(e), 'code': e.code}), 404
    except QuotaExhaustedError as e:
        return jsonify({'success': False, 'error': str(e), 'code': e.code}), 429
    except ProviderUnavailableError as e:
        return jsonify({'success': False, 'error': str(e), 'code': e.code}), 503
    except VINDecoderError as e:
        logger.exception(f'VIN decode failed for {vin}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

@carpark_bp.route('/api/carpark/vin/validate/<vin>', methods=['GET'])
@login_required
def validate_vin(vin):
    """Validate VIN format without decoding."""
    result = _vin_client.validate(vin)
    return jsonify({'success': True, 'data': result})

@carpark_bp.route('/api/carpark/vin/providers', methods=['GET'])
@login_required
def vin_provider_status():
    """Get status of VIN decoder providers."""
    status = _vin_client.get_provider_status()
    return jsonify({'success': True, 'data': status})
```

### FRONTEND INTEGRATION

Add a VIN lookup hook and component:

```typescript
// File: frontend/src/api/carpark.ts (add to existing carparkApi)
async decodeVIN(vin: string, refresh?: boolean) {
    const params = refresh ? { refresh: 'true' } : {}
    return (await api.get(`/api/carpark/vin/decode/${vin}`, { params })).data
},

async validateVIN(vin: string) {
    return (await api.get(`/api/carpark/vin/validate/${vin}`)).data
},
```

```typescript
// File: frontend/src/pages/CarPark/components/Detail/VINLookup.tsx
// Component that:
// 1. Renders a VIN input field with validation indicator (green check / red X)
// 2. Has a "Decode" button that calls the API
// 3. On success: shows a preview of decoded specs in a card/modal
// 4. Has a "Apply to Vehicle" button that populates the vehicle form fields
// 5. Shows provider name and confidence score
// 6. Debounced validation on input (validate after 500ms of no typing)
// 7. Loading state with spinner during API call
// 8. Error display for invalid VIN, not found, quota exhausted
```

### ENVIRONMENT VARIABLES TO ADD

```bash
# VIN Decoder — Vincario credentials (from vincario.com dashboard)
VINCARIO_API_KEY=2ce2ba1b881d
VINCARIO_SECRET_KEY=7bc47b0b00
VIN_PROVIDER_PRIORITY=vincario,nhtsa
VIN_CACHE_ENABLED=true
VIN_CACHE_TTL_DAYS=90
VIN_REQUEST_TIMEOUT=15
VINCARIO_MAX_REQUESTS=500
```

### MIGRATION TO ADD

```python
# File: jarvis/migrations/domains/schema_carpark_vin_cache.py
def create_schema_carpark_vin_cache(conn, cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carpark_vin_cache (
            id SERIAL PRIMARY KEY,
            vin VARCHAR(17) NOT NULL,
            provider VARCHAR(30) NOT NULL,
            specs_json JSONB NOT NULL,
            confidence_score DECIMAL(3,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            UNIQUE(vin, provider)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vin_cache_vin ON carpark_vin_cache(vin)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vin_cache_expires ON carpark_vin_cache(expires_at)')
```

### SCHEDULED TASK TO ADD

```python
# In tasks/cleanup.py — add cache cleanup
scheduler.add_job(
    vin_cache_cleanup,    # DELETE FROM carpark_vin_cache WHERE expires_at < NOW()
    'cron', hour=3, minute=0,
    id='carpark_vin_cache_cleanup',
    name='CarPark VIN Cache Cleanup'
)
```

## QUALITY REQUIREMENTS

1. **Follow JARVIS patterns exactly:** BaseRepository inheritance, logging with `get_logger`, structured extras, hashed payloads (never log API keys or raw responses), jsonify response format `{success, data/error}`, `@login_required` on all routes.

2. **Type hints everywhere.** Use Python type hints on all function signatures. Use TypeScript interfaces for all API responses.

3. **Error handling must be exhaustive.** Every `requests` call wrapped in try/except catching Timeout, ConnectionError, SSLError, RequestException. Map to custom exceptions. Log with context.

4. **Tests:** Write unit tests for:
   - VIN validation (valid VINs, invalid length, bad characters, bad check digit)
   - Mapper normalization (brand aliases, fuel type normalization, unit conversions)
   - Client failover (primary fails → fallback succeeds)
   - Cache hit/miss behavior
   - Provider status reporting

5. **No hardcoded secrets.** All API keys from environment variables via `VINDecoderConfig.from_env()`.

6. **Logging:** Use `logging.getLogger('jarvis.carpark.connectors.vin_decoder')`. Log every API call with method, endpoint, latency_ms, status_code. Hash payloads. Log provider failover events at WARNING level.

## EXECUTION ORDER

1. Create `exceptions.py`
2. Create `config.py`
3. Create `validator.py` with tests
4. Create `providers/base.py` with `VehicleSpecs` dataclass
5. Create `mapper.py` with tests
6. Create `providers/nhtsa_provider.py` (free, test immediately)
7. Create `providers/vincario_provider.py`
8. Create `cache.py` with migration
9. Create `client.py` (orchestrator)
10. Add routes to `routes.py`
11. Create frontend `VINLookup.tsx` component
12. Add frontend API methods
13. Run all tests
14. Test end-to-end with a real VIN (e.g., `YV1XZ98AWN1234567` for Volvo XC40)
