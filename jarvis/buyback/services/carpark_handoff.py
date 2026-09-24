"""CarPark hand-off — the payoff of the buyback module: turn a finalized
(BOUGHT) buyback record into a real CarPark vehicle draft, carry its photo
gallery over, and back-link the two records.

Called by buyback.routes.finalize (both the `/finalize` and
`/handoff/retry` routes) — see that module's docstring for the full
finalize/retry state machine this feeds into.

Import-cycle note: `carpark.services.vehicle_service` and
`carpark.repositories.*` are imported LOCALLY inside the functions that need
them (not at module top level). buyback/routes/_shared.py is imported at
module top level here (for photos_repo) — that's safe, `_shared` never
imports anything from `carpark`. The carpark imports are kept local purely
to keep this module a leaf that doesn't force carpark's whole import graph
to resolve just because `buyback` is imported somewhere (mirrors
records.py's own local `from carpark.repositories.vehicle_repository import
VehicleRepository` on CREATE, for the VIN-already-in-carpark heads-up).

VIN handling: VehicleService.create_vehicle raises ValueError on a missing/
duplicate VIN. That ValueError is NOT caught here — it propagates verbatim
to the caller (the finalize/retry route), which is exactly what makes the
"hand-off failed, record stays BOUGHT with carpark_vehicle_id still NULL,
retry later" behavior work. Once the vehicle row exists, though, a failure
carrying photos over or writing the back-link must NEVER undo that — both
_carry_photos and _backlink are best-effort: they log and swallow their own
exceptions rather than raising, so a Spaces hiccup or a stray FK issue never
turns a successful vehicle creation into a hand-off failure.
"""
import logging
from uuid import uuid4

from buyback.routes import _shared
from core.services import spaces_service

logger = logging.getLogger('jarvis.buyback')


def handoff_to_carpark(record, finalized_by) -> dict:
    """Create a CarPark vehicle draft from `record` (a BOUGHT buyback
    record), carry its photo gallery over to the new vehicle, and back-link
    the two records via carpark_vehicle_links. Returns the created CarPark
    vehicle dict.

    `record` is expected to already carry `purchase_price_eur` (the finalize
    route stamps it from the accepted FINAL offer before calling this).

    Raises ValueError verbatim from VehicleService.create_vehicle (e.g. an
    invalid/duplicate VIN) — see module docstring for why that is
    deliberate: the caller translates it into the retryable hand-off-failure
    response instead of a hard error.
    """
    source = 'BUY BACK PJ' if record.get('client_type') == 'company' else 'BUY BACK PF'
    manufacture_date = record.get('manufacture_date')

    data = {
        'vin': record['vin'],
        'brand': record['brand'],
        'model': record['model'],
        'variant': record.get('variant'),
        'manufacture_date': manufacture_date,
        'year_of_manufacture': manufacture_date.year if manufacture_date else None,
        'first_registration_date': record.get('first_registration_date'),
        'mileage_km': record.get('mileage_km'),
        'fuel_type': record.get('fuel_type'),
        'transmission': record.get('transmission'),
        'company_id': record['company_id'],  # explicit, server-side — never from HTTP input
        'status': 'ACQUIRED',
        'source': source,
        'category': 'TI' if record.get('is_trade_in') else 'SH',
        'supplier_name': record.get('seller_name'),
        'owner_name': record.get('seller_name'),
        'supplier_cif': record.get('seller_cui'),
        'purchase_price_net': record.get('purchase_price_eur'),
        'purchase_price_currency': 'EUR',
    }

    from carpark.services.vehicle_service import VehicleService
    veh = VehicleService().create_vehicle(data, created_by=finalized_by)  # may raise ValueError

    _carry_photos(record['id'], veh['id'])
    _backlink(veh['id'], record['id'], finalized_by)
    return veh


def _carry_photos(record_id, veh_id):
    """Copy every buyback gallery photo for `record_id` onto the new CarPark
    vehicle `veh_id`: fetch the original bytes from Spaces, re-upload under
    a fresh carpark-namespaced key, and create the corresponding
    carpark_vehicle_photos row. The first photo carried becomes the new
    vehicle's primary photo.

    Best-effort per-photo: the vehicle already exists by the time this runs,
    so ANY failure on a single photo (Spaces fetch/upload error, a bad row,
    ...) is logged and skipped rather than raised — one bad photo must never
    cost the whole hand-off.
    """
    from carpark.repositories.photo_repository import PhotoRepository as CarparkPhotoRepository

    photos = _shared.photos_repo.get_by_record(record_id)
    if not photos:
        return

    carpark_photos = CarparkPhotoRepository()
    for idx, photo in enumerate(photos):
        try:
            data, _content_type = spaces_service.fetch(photo['url'])
            new_key = f'private/carpark/{veh_id}/{uuid4().hex}.jpg'
            spaces_service.upload(data, new_key, 'image/jpeg')
            carpark_photos.create(veh_id, url=new_key, is_primary=(idx == 0))
        except Exception:
            logger.warning(
                'CarPark hand-off: failed to carry photo id=%s (buyback record=%s) '
                'to vehicle=%s', photo.get('id'), record_id, veh_id, exc_info=True,
            )


def _backlink(veh_id, record_id, linked_by):
    """Create the carpark_vehicle_links row tying the new vehicle back to
    the buyback record it was created from (linked_entity_type='buyback').

    `linked_by` is required by carpark_vehicle_links' schema (`linked_by
    INTEGER NOT NULL REFERENCES users(id)`, unlike buyback's own
    created_by/finalized_by columns, which are bare integers with no FK) —
    the finalizing user is the natural value to attribute the link to.

    Best-effort: logged and swallowed on failure (e.g. a stray FK/constraint
    issue), never raised — the vehicle is already created, so this must not
    turn a successful hand-off into a failure.
    """
    try:
        from carpark.repositories.link_repository import VehicleLinkRepository
        VehicleLinkRepository().link(veh_id, 'buyback', record_id, linked_by)
    except Exception:
        logger.warning(
            'CarPark hand-off: failed to back-link vehicle=%s to buyback record=%s',
            veh_id, record_id, exc_info=True,
        )
