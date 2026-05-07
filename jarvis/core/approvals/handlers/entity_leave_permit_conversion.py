"""leave_permit_conversion entity handlers."""
import logging

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_lpc')


def handle_approved(entity_id, request_id, requester_id):
    """On approval: deduct CO, mark submissions converted."""
    try:
        from core.connectors.connecteam.repositories.conversion_repository import ConversionRepository
        from hr.co_balance.repository import CoBalanceRepository
        from core.base_repository import BaseRepository

        conv_repo = ConversionRepository()
        co_repo = CoBalanceRepository()
        base = BaseRepository()

        conversion = conv_repo.get_by_id(entity_id)
        if not conversion:
            logger.error(f'Conversion #{entity_id} not found')
            return

        # 1. Update conversion status
        conv_repo.update_status(entity_id, 'approved')

        # 2. Deduct from CO balance (negative delta)
        co_repo.adjust_manual(
            conversion['employee_user_id'],
            conversion['year'],
            -conversion['co_days_requested'],
        )

        # 3. Mark related submissions as 'converted'
        submission_ids = conv_repo.get_submission_ids(entity_id)
        for sid in submission_ids:
            base.execute(
                "UPDATE connecteam_form_submissions SET status = 'converted' WHERE submission_id = %s",
                (sid,),
            )

        # 4. Debit Time Bank (hours_converted = co_days * 8)
        try:
            from hr.time_bank.service import TimeBankService
            hours = conversion['co_days_requested'] * 8
            TimeBankService().debit(
                user_id=conversion['employee_user_id'],
                amount=hours,
                tx_type='co_conversion',
                description=f'CO conversion: {hours}h -> {conversion["co_days_requested"]} days CO',
                reference_type='co_conversion',
                reference_id=entity_id,
                created_by=None,
            )
        except Exception as tb_err:
            logger.warning(f'Time Bank debit failed for conversion #{entity_id}: {tb_err}')

        logger.info(
            f'Leave permit conversion #{entity_id} approved: '
            f'{conversion["co_days_requested"]} CO days deducted for user {conversion["employee_user_id"]}'
        )
    except Exception as e:
        logger.error(f'Failed to apply leave permit conversion on approval: {e}', exc_info=True)


def handle_rejected(entity_id, request_id):
    """On rejection: update conversion status."""
    try:
        from core.connectors.connecteam.repositories.conversion_repository import ConversionRepository
        ConversionRepository().update_status(entity_id, 'rejected')
        logger.info(f'Leave permit conversion #{entity_id} rejected')
    except Exception as e:
        logger.error(f'Failed to reject leave permit conversion: {e}', exc_info=True)
