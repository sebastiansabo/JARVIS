"""Shared fp_vehicles create-validation — single source of truth.

Extracted verbatim out of the manual Add-Vehicle route (POST
/api/foi-parcurs/vehicles, see foi_parcurs/routes/vehicles.py) so a later
CarPark -> Driving Hub fleet "push" path can create fp_vehicles rows through
the exact same validation/payload-build rules, with no risk of drifting from
the manual-add behavior.
"""

import logging

from ..document_types import normalize as _normalize_doctype
from ..repositories import FPVehicleRepository

logger = logging.getLogger('jarvis.foi_parcurs.routes')

# Module-level singleton — the default `repo` for production callers that
# don't wire one up themselves. Tests inject a mock/fake via the `repo` kwarg.
_default_repo = FPVehicleRepository()

_VALID_FUEL_TYPES = ('Benzina', 'Diesel', 'Electric', 'Hybrid', 'Plug-in Hybrid')

# Capacity-by-fuel-type — mirrors route_sheet_service: a plain Hybrid (HEV) has
# a tank only; only Electric and Plug-in Hybrid (PHEV) charge a traction battery.
_USES_TANK = ('Benzina', 'Diesel', 'Hybrid', 'Plug-in Hybrid')
_USES_BATTERY = ('Electric', 'Plug-in Hybrid')


def _to_int_or_none(value):
    """Coerce to int, or None if empty/invalid."""
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_num_or_none(value):
    """Coerce to a number (allows decimals, e.g. 1.8 kWh), or None if empty/invalid."""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def create_fp_vehicle(data, *, repo=None):
    """Validate + create a single fp_vehicles row.

    Returns ``(vehicle_dict, None)`` on success, or ``(None, (message, http_status))``
    on failure. Failure codes: missing vin/mark/model -> 400; bad fuel_type ->
    400; missing tank/battery capacity for the given fuel_type -> 400;
    duplicate VIN -> 409.

    ``repo`` defaults to a module-level ``FPVehicleRepository()``; callers that
    need to share a single singleton (e.g. so tests can monkeypatch it) should
    pass their own instance explicitly.
    """
    repo = repo or _default_repo

    vin = (data.get('vin') or '').strip().upper()
    mark = (data.get('mark') or '').strip()
    model = (data.get('model') or '').strip()

    if not vin:
        return None, ('VIN is required', 400)
    if not mark:
        return None, ('Mark is required', 400)
    if not model:
        return None, ('Model is required', 400)

    # Check duplicate VIN
    existing = repo.get_by_vin(vin)
    if existing:
        return None, (f'Vehicle with VIN {vin} already exists', 409)

    fuel_type = (data.get('fuel_type') or 'Diesel').strip()
    if fuel_type not in _VALID_FUEL_TYPES:
        return None, ('fuel_type must be Benzina, Diesel, Electric, Hybrid, or Plug-in Hybrid', 400)

    uses_tank = fuel_type in _USES_TANK
    uses_batt = fuel_type in _USES_BATTERY
    fuel_liters = _to_num_or_none(data.get('fuel_tank_capacity_liters'))
    battery_kwh = _to_num_or_none(data.get('battery_capacity_kwh'))
    if uses_tank and not fuel_liters:
        return None, ('Fuel capacity (L) is required for this fuel type', 400)
    if uses_batt and not battery_kwh:
        return None, ('Battery capacity (kWh) is required for this fuel type', 400)
    if not uses_tank:
        fuel_liters = None
    if not uses_batt:
        battery_kwh = None

    company_id = data.get('company_id')
    if company_id is not None:
        try:
            company_id = int(company_id)
        except (ValueError, TypeError):
            company_id = None

    # Only the INSERT is guarded — mirrors the original route, where an
    # exception from repo.create() surfaced as (str(e)[:300], 500) while any
    # failure in the (unguarded) validation / duplicate-VIN lookup above
    # propagated to the app's global errorhandler. Keep that boundary exact.
    try:
        vehicle = repo.create({
            'vin': vin,
            'registration_number': (data.get('registration_number') or '').strip().upper() or None,
            'car_id': (data.get('car_id') or '').strip() or None,
            'mark': mark,
            'brand': (data.get('brand') or '').strip() or None,
            'model': model,
            'color': (data.get('color') or '').strip() or None,
            'fuel_type': fuel_type,
            'fuel_tank_capacity_liters': fuel_liters,
            'battery_capacity_kwh': battery_kwh,
            'odometer_km': _to_int_or_none(data.get('odometer_km')),
            'norma_combustibil': _to_num_or_none(data.get('norma_combustibil')),
            'norma_energie': _to_num_or_none(data.get('norma_energie')),
            'category': (data.get('category') or '').strip() or None,
            'company_id': company_id,
            'document_type': _normalize_doctype(data.get('document_type')),
            # Service (Mașini de curtoazie) price + tariffs-policy override —
            # NULL falls back to the company default (resolve_policy in
            # rental_pricing.py). Harmless for Sales cars (never read).
            'svc_tariff_eur_day': _to_num_or_none(data.get('svc_tariff_eur_day')),
            'svc_tariff_eur_month': _to_num_or_none(data.get('svc_tariff_eur_month')),
            'svc_km_included_day': _to_int_or_none(data.get('svc_km_included_day')),
            'svc_extra_km_eur': _to_num_or_none(data.get('svc_extra_km_eur')),
            'svc_deposit_eur': _to_num_or_none(data.get('svc_deposit_eur')),
            'svc_franchise_eur': _to_num_or_none(data.get('svc_franchise_eur')),
            'vignette_valid_until': (data.get('vignette_valid_until') or '').strip() or None,
            'itp_valid_until': (data.get('itp_valid_until') or '').strip() or None,
            'insurance_valid_until': (data.get('insurance_valid_until') or '').strip() or None,
            'insurance_doc': data.get('insurance_doc') or None,
            'talon_doc': data.get('talon_doc') or None,
            'civ_doc': data.get('civ_doc') or None,
            'registration_doc': data.get('registration_doc') or None,
            'offer_doc': data.get('offer_doc') or None,
        })
    except Exception as e:
        logger.exception('Failed to create vehicle')
        return None, (str(e)[:300], 500)
    return vehicle, None
