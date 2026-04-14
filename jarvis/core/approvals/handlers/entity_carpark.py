"""carpark_price_change entity handlers."""
import logging

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_carpark')


def handle_approved(entity_id, request_id, requester_id):
    try:
        from carpark.repositories.pricing_repository import PricingRepository
        from carpark.repositories.vehicle_repository import VehicleRepository
        pricing_repo = PricingRepository()
        vehicle_repo = VehicleRepository()
        changes = pricing_repo.get_pending_changes(approval_request_id=request_id, status='pending')
        for ch in changes:
            vehicle_repo.update(ch['vehicle_id'], {'current_price': float(ch['new_price'])})
            pricing_repo.log_price_change(
                ch['vehicle_id'], float(ch['old_price']), float(ch['new_price']),
                f'approved:rule#{entity_id}', rule_id=entity_id, changed_by=requester_id,
            )
        pricing_repo.update_pending_status(request_id, 'approved', applied_by=requester_id)
        logger.info(f'CarPark price changes approved for rule #{entity_id}: {len(changes)} vehicles updated')
    except Exception as e:
        logger.error(f'Failed to apply carpark price changes on approval: {e}', exc_info=True)


def handle_rejected(entity_id, request_id):
    try:
        from carpark.repositories.pricing_repository import PricingRepository
        PricingRepository().update_pending_status(request_id, 'rejected')
        logger.info(f'CarPark price changes rejected for rule #{entity_id}')
    except Exception as e:
        logger.error(f'Failed to reject carpark price changes: {e}', exc_info=True)
