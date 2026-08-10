"""CarPark scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.carpark')


def cleanup_vin_cache():
    """Delete expired VIN decoder cache entries."""
    try:
        from carpark.connectors.vin_decoder.cache import VINCache
        cache = VINCache()
        count = cache.cleanup_expired()
        if count > 0:
            logger.info(f"Cleanup: deleted {count} expired VIN cache entries")
    except Exception as e:
        logger.error(f"VIN cache cleanup task failed: {e}")


def expire_reservations():
    """Hourly: close out reservations whose reservation_end has passed.

    For every active reservation returned by ReservationRepository.expired()
    (reservation_end < today): mark the reservation 'expired', move the
    vehicle back RESERVED -> LISTED, and notify the reservation's user_id.

    Guarded against races with a manual sale/delivery in the same window:
    only touches the vehicle status if it's still RESERVED (a vehicle that
    was sold/delivered out from under an overdue reservation must not be
    yanked back to LISTED). Each reservation is processed in its own
    try/except so one bad row can't abort the whole batch.
    """
    try:
        from datetime import date
        from carpark.repositories.reservation_repository import ReservationRepository
        from carpark.repositories.vehicle_repository import VehicleRepository
        from carpark.services.vehicle_service import VehicleService
        from core.notifications.notify import notify_user

        reservation_repo = ReservationRepository()
        vehicle_repo = VehicleRepository()
        vehicle_service = VehicleService()

        today = date.today()
        expired = reservation_repo.expired(today)
        if not expired:
            logger.debug('No expired reservations')
            return

        expired_count = 0
        for reservation in expired:
            reservation_id = reservation.get('id')
            vehicle_id = reservation.get('vehicle_id')
            try:
                reservation_repo.set_status(reservation_id, 'expired')

                vehicle = vehicle_repo.get_by_id(vehicle_id)
                if not vehicle or vehicle.get('status') != 'RESERVED':
                    # Vehicle already moved on (sold/delivered/reopened) since
                    # the reservation lapsed — don't fight that transition.
                    continue

                vehicle_service.change_status(
                    vehicle_id, 'LISTED', changed_by=None,
                    notes='Reservation expired')

                user_id = reservation.get('user_id')
                if user_id:
                    label = f"{vehicle.get('brand', '')} {vehicle.get('model', '')}".strip()
                    notify_user(
                        user_id, 'Rezervare expirată',
                        message=f'Rezervarea pentru {label or vehicle.get("vin")} a expirat.',
                        entity_type='carpark_vehicle', entity_id=vehicle_id)

                expired_count += 1
            except Exception:
                logger.warning(
                    'Failed to expire reservation %s (vehicle %s)',
                    reservation_id, vehicle_id, exc_info=True)

        logger.info(f'Expired {expired_count} of {len(expired)} reservation(s)')
    except Exception as e:
        logger.error(f'Reservation expiry job failed: {e}', exc_info=True)


def carpark_aging_alerts():
    """Daily (08:00): notify on vehicles that have sat unsold too long.

    Queries DispoRepository.aged_unsold(60) — unsold vehicles (not
    SOLD/DELIVERED/SCRAPPED/TRANSFERRED/RETURNED, not soft-deleted) whose
    days_in_stock exceeds 60 — and notifies each vehicle's salesperson,
    falling back to its acquisition manager.

    Note: the domain has no dedicated "sales manager" role/table, so this
    maps to the same salesperson/acquisition-manager target DispoService
    uses for every other lifecycle notification (see
    DispoService._notify_vehicle_contacts). No per-vehicle cooldown (unlike
    foi_parcurs' 7-day smart_notification_state cooldown) — this fires once
    per vehicle every day it stays aged, which is acceptable for an initial
    daily digest-style alert; a cooldown table would be a follow-up if this
    proves too noisy in practice.
    """
    try:
        from carpark.repositories.dispo_repository import DispoRepository
        from core.notifications.notify import notify_user

        repo = DispoRepository()
        aged = repo.aged_unsold(60)
        if not aged:
            logger.debug('No vehicles aged over 60 days in stock')
            return

        notified = 0
        for vehicle in aged:
            vehicle_id = vehicle.get('id')
            try:
                target_user_id = (vehicle.get('salesperson_user_id')
                                   or vehicle.get('acquisition_manager_id'))
                if not target_user_id:
                    continue

                label = f"{vehicle.get('brand', '')} {vehicle.get('model', '')}".strip() \
                    or vehicle.get('vin')
                notify_user(
                    target_user_id, 'Vehicul cu vechime mare în stoc',
                    message=(f'{label} ({vehicle.get("vin")}) este în stoc de '
                             f'{vehicle.get("days_in_stock")} zile.'),
                    entity_type='carpark_vehicle', entity_id=vehicle_id)
                notified += 1
            except Exception:
                logger.warning('Aging alert failed for vehicle %s', vehicle_id, exc_info=True)

        logger.info(f'Sent {notified} of {len(aged)} aging alert(s)')
    except Exception as e:
        logger.error(f'Carpark aging alert job failed: {e}', exc_info=True)
