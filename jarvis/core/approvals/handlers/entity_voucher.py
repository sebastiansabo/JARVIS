"""Approval hook handler for voucher entities."""
import logging

logger = logging.getLogger('jarvis.approvals.handlers.voucher')


def handle_approved(entity_id, request_id=None, requester_id=None):
    """Called when a voucher approval request is approved."""
    try:
        from accounting.vouchers.services import VoucherService
        VoucherService().activate_voucher(entity_id)
        logger.info('Voucher #%s activated via approval hook', entity_id)
    except Exception as e:
        logger.error('Failed to activate voucher #%s: %s', entity_id, e, exc_info=True)


def handle_rejected(entity_id, comment=None):
    """Called when a voucher approval request is rejected."""
    try:
        from accounting.vouchers.services import VoucherService
        VoucherService().reject_voucher(entity_id, reason=comment)
        logger.info('Voucher #%s rejected via approval hook', entity_id)
    except Exception as e:
        logger.error('Failed to reject voucher #%s: %s', entity_id, e, exc_info=True)
