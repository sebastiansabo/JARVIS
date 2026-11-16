"""CarPark -> Driving Hub fleet push — pure mapping + orchestration.

This is Task 2 of the CarPark -> Driving Hub fleet push feature: it turns a
CarPark `carpark_vehicles` row into a Driving Hub `fp_vehicles` row.

  - `map_fuel_to_fleet` / `build_suggested` are pure mapping helpers (no I/O):
    given a CarPark fuel string / vehicle dict, they compute the Driving Hub
    fleet's equivalent.
  - `get_fleet_status` is a read-only lookup: is this VIN already in the
    Driving Hub fleet (and if so, is it archived)?
  - `push_to_fleet` is the orchestration: resolve + authorize a company,
    short-circuit a duplicate VIN, then create the fp_vehicles row through
    the SAME validation `create_fp_vehicle` (Task 1,
    foi_parcurs/services/vehicle_create.py) uses for the manual Add-Vehicle
    form, so a pushed car can never drift from that validation. On success,
    it best-effort flags the source carpark_vehicles row as
    `is_test_drive = TRUE` (via `VehicleRepository.set_test_drive` — the raw
    SQL lives in the repository, never here) — a failure there is logged and
    swallowed; it must never fail the push itself (the fp_vehicles row is
    already committed).

Error channel: `push_to_fleet` returns `(result, err)` where `err`, when not
None, is a dict `{'status': <http_status>, 'message': <str>, **extra}` — a
later route task (Task 3) maps this dict uniformly to an HTTP response, and
the frontend (Task 4) reads `err['status'] == 409` + `err['fp_vehicle_id']`
to flip its own UI to "already in fleet" instead of showing a hard error.

Module-level `_fp_repo` / `_vehicle_repo` singletons (mirrors the
`_default_repo` idiom in foi_parcurs/services/vehicle_create.py and the
`r._taxonomy_repo` / `r._photo_repo` singletons in carpark/connectors/autovit/
routes.py) — tests monkeypatch these directly rather than threading repo
kwargs through every call site.
"""

import logging

from carpark.connectors.autovit.taxonomy_map import resolve_enum
from carpark.repositories.vehicle_repository import VehicleRepository
from foi_parcurs.repositories import FPVehicleRepository
from foi_parcurs.services.vehicle_create import create_fp_vehicle

logger = logging.getLogger('jarvis.carpark.driving_hub_push_service')

_fp_repo = FPVehicleRepository()
_vehicle_repo = VehicleRepository()

# CarPark fuel_type -> Autovit taxonomy slug (via resolve_enum('fuel_type', ...))
# -> Driving Hub fp_vehicles.fuel_type enum. Any slug not listed here (or a
# carpark fuel_type resolve_enum can't resolve at all) maps to None — the
# push dialog (Task 4) then forces the user to pick a fuel type manually
# rather than silently guessing one.
_SLUG_TO_FLEET = {
    'petrol': 'Benzina',
    'diesel': 'Diesel',
    'electric': 'Electric',
    'hybrid': 'Hybrid',
    'mild-hybrid-petrol': 'Hybrid',
    'mild-hybrid-diesel': 'Hybrid',
    'plugin-hybrid': 'Plug-in Hybrid',
    'petrol-lpg': 'Benzina',
    'petrol-cng': 'Benzina',
    'hydrogen': 'Benzina',
    'ethanol': 'Benzina',
}


def map_fuel_to_fleet(carpark_fuel):
    """CarPark `fuel_type` string -> Driving Hub fleet fuel enum, or None if
    unresolved/unknown. Routes through the SAME keyword resolver the Autovit
    taxonomy mapping uses (`resolve_enum('fuel_type', ...)`) so a value like
    'Motorină' or 'mild hybrid petrol' resolves by meaning, not exact string
    match; the resolved Autovit slug (`target_label`) is then mapped onto the
    fleet's own (narrower) enum via `_SLUG_TO_FLEET`."""
    if not carpark_fuel:
        return None
    resolved = resolve_enum('fuel_type', carpark_fuel)
    if not resolved:
        return None
    return _SLUG_TO_FLEET.get(resolved.get('target_label'))


def build_suggested(carpark_vehicle):
    """Map a CarPark vehicle dict to the fields a Driving Hub fp_vehicles row
    would suggest-prefill: `{mark, brand, model, registration_number,
    fuel_type, company_id, odometer_km, color}`. Capacity keys
    (fuel_tank_capacity_liters/battery_capacity_kwh) are deliberately omitted
    — CarPark carries no equivalent field, and `create_fp_vehicle`'s own
    validation requires them only for the fuel types that need them."""
    carpark_vehicle = carpark_vehicle or {}
    brand = carpark_vehicle.get('brand')
    return {
        'mark': brand,
        'brand': brand,
        'model': carpark_vehicle.get('model'),
        'registration_number': carpark_vehicle.get('registration_number'),
        'fuel_type': map_fuel_to_fleet(carpark_vehicle.get('fuel_type')),
        'company_id': carpark_vehicle.get('company_id'),
        'odometer_km': carpark_vehicle.get('mileage_km'),
        'color': carpark_vehicle.get('color_exterior'),
    }


def _normalized_vin(carpark_vehicle):
    return ((carpark_vehicle or {}).get('vin') or '').strip().upper()


def get_fleet_status(carpark_vehicle):
    """Is `carpark_vehicle` (by VIN) already a Driving Hub fp_vehicles row?

    Returns `{'in_fleet': bool, 'archived': bool, 'fp_vehicle_id': int|None,
    'suggested': dict}` — `suggested` is always populated (from
    `build_suggested`) so the push dialog (Task 4) has prefill values
    whether or not the car is already in the fleet."""
    vin = _normalized_vin(carpark_vehicle)
    existing = _fp_repo.get_by_vin(vin) if vin else None
    return {
        'in_fleet': existing is not None,
        'archived': bool(existing) and not existing.get('is_active', True),
        'fp_vehicle_id': existing.get('id') if existing else None,
        'suggested': build_suggested(carpark_vehicle),
    }


def push_to_fleet(carpark_vehicle, overrides, actable_company_ids, *, is_admin):
    """Create a Driving Hub fp_vehicles row from `carpark_vehicle`, applying
    `overrides` (company_id / fuel_type / capacity / plate corrections from
    the push dialog) on top of `build_suggested`'s prefill.

    Returns `(result, err)`:
      - success -> `({'fp_vehicle_id': <new id>}, None)`
      - failure -> `(None, {'status': <code>, 'message': <str>, **extra})`

    Guard order (each short-circuits the next): resolve an effective
    company_id (overrides win over the carpark car's own) -> 400 if none;
    authorize it against `actable_company_ids` unless `is_admin` -> 403;
    look up the VIN directly (BEFORE calling create_fp_vehicle, so the 409
    can carry the existing fp_vehicle_id for the route/UI to flip to
    "already in fleet") -> 409 if found; otherwise delegate the actual
    insert to `create_fp_vehicle` (Task 1), translating its `(message, code)`
    tuple error into this function's dict error shape.
    """
    carpark_vehicle = carpark_vehicle or {}
    overrides = overrides or {}
    actable_company_ids = actable_company_ids or set()

    raw_company_id = overrides.get('company_id') or carpark_vehicle.get('company_id')
    if not raw_company_id:
        return None, {'status': 400, 'message': 'Selectează o companie'}
    try:
        company_id = int(raw_company_id)
    except (TypeError, ValueError):
        return None, {'status': 400, 'message': 'Selectează o companie'}

    if not is_admin and company_id not in actable_company_ids:
        return None, {'status': 403, 'message': 'Companie neautorizată'}

    vin = _normalized_vin(carpark_vehicle)
    existing = _fp_repo.get_by_vin(vin) if vin else None
    if existing:
        return None, {
            'status': 409,
            'message': 'Vehiculul este deja în flota Driving Hub',
            'fp_vehicle_id': existing.get('id'),
        }

    suggested = build_suggested(carpark_vehicle)

    # Brand is tenant-scoped catalog data, so validate it server-side (like the
    # company check) — never trust the client. The Driving Hub filters its
    # stock / Test-Drive car pickers by the EXACT catalog string
    # (`v.brand === brand`), so a pushed car whose brand isn't one of the
    # company's sales-catalog labels is created fine but stays SILENTLY INVISIBLE
    # in the hub (the known fp_vehicles brand-label gotcha). Effective brand =
    # the dialog's chosen catalog label (override) or the CarPark make as a
    # fallback; it must be a real catalog label whenever a catalog exists.
    effective_brand = overrides.get('brand') or suggested.get('mark')
    catalog = _fp_repo.list_sales_brand_labels(company_id)
    if catalog and effective_brand not in catalog:
        return None, {'status': 400, 'message': 'Selectează o marcă validă din flotă'}
    # Empty catalog (courtesy/rental-only company) -> no catalog to match
    # against, so the make fallback is allowed through as-is.

    payload = {**suggested, **overrides}
    payload['vin'] = vin
    payload['company_id'] = company_id
    payload['document_type'] = 'sales'
    payload['brand'] = effective_brand
    payload['mark'] = overrides.get('mark') or suggested.get('mark')

    vehicle, err = create_fp_vehicle(payload, repo=_fp_repo)
    if err:
        message, status = err
        return None, {'status': status, 'message': message}

    carpark_vehicle_id = carpark_vehicle.get('id')
    if carpark_vehicle_id is not None:
        try:
            _vehicle_repo.set_test_drive(carpark_vehicle_id, True)
        except Exception:
            # Best-effort only — the fp_vehicles row is already committed;
            # this flag just helps CarPark's own list reflect the push.
            logger.warning(
                'Driving Hub push: fp_vehicle %s created but failed to flag '
                'carpark vehicle %s as is_test_drive',
                vehicle.get('id'), carpark_vehicle_id, exc_info=True,
            )

    return {'fp_vehicle_id': vehicle['id']}, None
