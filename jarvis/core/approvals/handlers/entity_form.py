"""form_submission entity handlers."""
import logging
from ._shared import _notify_form_submission_users, _send_approval_email, _approval_email_base, _APP_BASE_URL

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_form')


def handle_submitted(entity_id, ctx):
    """Set form_submission to pending_approval on submit."""
    try:
        from forms.repositories import SubmissionRepository
        sub_repo = SubmissionRepository()
        sub_repo.update_status(entity_id, 'pending_approval')

        # Create voucher immediately so it appears in issuer's list as pending_approval
        _create_voucher_on_submit(entity_id, sub_repo)
    except Exception as e:
        logger.error(f'Failed to set form_submission pending_approval on submit: {e}')


def handle_approved(entity_id, ctx):
    """Set form_submission to approved and send notifications."""
    try:
        from forms.repositories import SubmissionRepository
        sub_repo = SubmissionRepository()
        sub_repo.update_status(entity_id, 'approved')
        logger.info(f'Form submission #{entity_id} status set to approved via approval hook')

        # Debit Time Bank for approved bilet-de-invoire submissions
        _debit_leave_permit_hours(entity_id, sub_repo)

        # Activate voucher for approved voucher-issuance submissions
        _activate_voucher_from_submission(entity_id, sub_repo)
    except Exception as e:
        logger.error(f'Failed to update form_submission status on approval: {e}')
    project_title = ctx.get('title') or f'form_submission #{entity_id}'
    _notify_form_submission_users(ctx, 'notify_on_approve', project_title, 'approved')
    if ctx.get('notify_respondent') and ctx.get('respondent_email'):
        _send_approval_email(
            ctx['respondent_email'],
            f'Your submission has been approved: {project_title}',
            _approval_email_base(
                'Submission Approved',
                f'<p>Your submission to <strong>{ctx.get("form_name", "")}</strong> has been approved.</p>',
                f'{_APP_BASE_URL}/f/{ctx.get("form_name", "")}',
                'View Form',
            ),
        )


def handle_rejected(entity_id, ctx, note=''):
    """Set form_submission to rejected and send notifications."""
    try:
        from forms.repositories import SubmissionRepository
        sub_repo = SubmissionRepository()
        sub_repo.update_status(entity_id, 'rejected')
        logger.info(f'Form submission #{entity_id} status set to rejected via approval hook')

        # Reject the linked voucher
        _reject_voucher_from_submission(entity_id, sub_repo, note)
    except Exception as e:
        logger.error(f'Failed to update form_submission status on rejection: {e}')
    project_title = ctx.get('title') or f'form_submission #{entity_id}'
    _notify_form_submission_users(ctx, 'notify_on_reject', project_title, 'rejected')
    if ctx.get('notify_respondent') and ctx.get('respondent_email'):
        note_text = f'<p><strong>Reason:</strong> {note}</p>' if note else ''
        _send_approval_email(
            ctx['respondent_email'],
            f'Your submission has been rejected: {project_title}',
            _approval_email_base(
                'Submission Rejected',
                f'<p>Your submission to <strong>{ctx.get("form_name", "")}</strong> has been rejected.</p>{note_text}',
                f'{_APP_BASE_URL}/f/{ctx.get("form_name", "")}',
                'View Form',
            ),
        )


def _debit_leave_permit_hours(submission_id, sub_repo):
    """Debit Time Bank hours when a bilet-de-invoire form is approved."""
    try:
        from core.connectors.connecteam.config import JARVIS_LEAVE_FORM_SLUG
        from forms.repositories import FormRepository

        sub = sub_repo.get_by_id(submission_id)
        if not sub:
            return
        form = FormRepository().get_by_id(sub['form_id'])
        if not form or form.get('slug') != JARVIS_LEAVE_FORM_SLUG:
            return

        answers = sub.get('answers') or {}
        hours = float(answers.get('f_bi_hours') or 0)
        leave_date = answers.get('f_bi_leave_date', '')
        user_id = sub.get('respondent_user_id')

        if not user_id or hours <= 0:
            return

        from hr.time_bank.service import TimeBankService
        TimeBankService().debit(
            user_id=user_id,
            amount=hours,
            tx_type='leave_permit',
            description=f'Bilet de invoire: {hours}h on {leave_date or "N/A"}',
            reference_type='form_submission',
            reference_id=submission_id,
            created_by=None,
        )
        logger.info(f'Time Bank debit {hours}h for form_submission #{submission_id}')
    except Exception as e:
        logger.error(f'Time Bank debit failed for form_submission #{submission_id}: {e}')


def _resolve_voucher_company(sub, form):
    """Get company_id from the submitting user, falling back to form/submission."""
    user_id = sub.get('respondent_user_id')
    if user_id:
        try:
            from core.base_repository import BaseRepository
            user = BaseRepository().query_one('SELECT company_id FROM users WHERE id = %s', (user_id,))
            if user and user.get('company_id'):
                return user['company_id']
        except Exception:
            pass
    return sub.get('company_id') or form.get('company_id')


def _parse_voucher_fields(answers):
    """Parse voucher fields from form answers. Shared by submit and create flows."""
    # Parse validity months from dropdown label
    validity_label = answers.get('f_validity_months', '12 months')
    validity_months = int(str(validity_label).split()[0]) if validity_label else 12

    # Map type label to enum
    type_map = {
        'Value (LEI)': 'value',
        'Accessory Discount Code': 'accessory_discount_code',
        'Accessory Percentage': 'accessory_percentage',
        'Service Items': 'service_items',
    }
    voucher_type = type_map.get(answers.get('f_voucher_type', ''), 'value')

    # Parse service items from multi-line text
    service_items = None
    if voucher_type == 'service_items':
        raw = answers.get('f_service_items', '')
        if isinstance(raw, list):
            service_items = [s.strip() for s in raw if s.strip()]
        else:
            service_items = [s.strip() for s in str(raw).split('\n') if s.strip()]

    # Parse numeric fields
    value_lei = None
    if voucher_type == 'value':
        try:
            value_lei = float(answers.get('f_value_lei', 0))
        except (TypeError, ValueError):
            value_lei = 0

    discount_percentage = None
    if voucher_type == 'accessory_percentage':
        try:
            discount_percentage = float(answers.get('f_discount_percentage', 0))
        except (TypeError, ValueError):
            discount_percentage = 0

    discount_code = None
    if voucher_type == 'accessory_discount_code':
        discount_code = str(answers.get('f_discount_code', '')).strip()

    return {
        'validity_months': validity_months,
        'voucher_type': voucher_type,
        'service_items': service_items,
        'value_lei': value_lei,
        'discount_percentage': discount_percentage,
        'discount_code': discount_code,
    }


def _is_voucher_submission(submission_id, sub_repo):
    """Check if a form submission is for the voucher-issuance form. Returns (sub, form) or (None, None)."""
    from accounting.vouchers.form_seed import VOUCHER_FORM_SLUG
    from forms.repositories import FormRepository

    sub = sub_repo.get_by_id(submission_id)
    if not sub:
        return None, None
    form = FormRepository().get_by_id(sub['form_id'])
    if not form or form.get('slug') != VOUCHER_FORM_SLUG:
        return None, None
    return sub, form


def _create_voucher_on_submit(submission_id, sub_repo):
    """Create a voucher with pending_approval status when form is submitted."""
    try:
        sub, form = _is_voucher_submission(submission_id, sub_repo)
        if not sub:
            return

        answers = sub.get('answers') or {}
        fields = _parse_voucher_fields(answers)

        from accounting.vouchers.repositories import VoucherRepository
        repo = VoucherRepository()
        voucher = repo.create(
            company_id=_resolve_voucher_company(sub, form),
            issued_by_user_id=sub.get('respondent_user_id') or form.get('owner_id'),
            client_name=str(answers.get('f_client_name', '')).strip(),
            contract_number=str(answers.get('f_contract_number', '')).strip(),
            car_vin=str(answers.get('f_car_vin', '')).strip().upper(),
            validity_months=fields['validity_months'],
            voucher_type=fields['voucher_type'],
            value_lei=fields['value_lei'],
            discount_code=fields['discount_code'],
            discount_percentage=fields['discount_percentage'],
            service_items=fields['service_items'],
            notes=str(answers.get('f_notes', '')).strip() or None,
            client_email=str(answers.get('f_client_email', '')).strip() or None,
            form_submission_id=submission_id,
        )
        # Status is already 'pending_approval' from repo.create()

        logger.info(f'Voucher {voucher["voucher_code"]} created (pending_approval) from form_submission #{submission_id}')
    except Exception as e:
        logger.error(f'Voucher creation on submit failed for form_submission #{submission_id}: {e}', exc_info=True)


def _find_voucher_by_submission(submission_id):
    """Find voucher linked to a form submission via form_submission_id column."""
    from core.base_repository import BaseRepository
    row = BaseRepository().query_one(
        'SELECT id FROM vouchers WHERE form_submission_id = %s', (submission_id,)
    )
    return row['id'] if row else None


def _activate_voucher_from_submission(submission_id, sub_repo):
    """Activate the voucher linked to an approved form submission."""
    try:
        sub, _ = _is_voucher_submission(submission_id, sub_repo)
        if not sub:
            return

        voucher_id = _find_voucher_by_submission(submission_id)
        if not voucher_id:
            # Fallback: create + activate if no linked voucher (handles old submissions)
            _create_voucher_from_submission_legacy(submission_id, sub_repo)
            return

        from accounting.vouchers.services import VoucherService
        VoucherService().activate_voucher(voucher_id)

        logger.info(f'Voucher #{voucher_id} activated from form_submission #{submission_id}')
    except Exception as e:
        logger.error(f'Voucher activation failed for form_submission #{submission_id}: {e}', exc_info=True)


def _reject_voucher_from_submission(submission_id, sub_repo, note=''):
    """Reject the voucher linked to a rejected form submission."""
    try:
        sub, _ = _is_voucher_submission(submission_id, sub_repo)
        if not sub:
            return

        voucher_id = _find_voucher_by_submission(submission_id)
        if not voucher_id:
            return

        from accounting.vouchers.services import VoucherService
        VoucherService().reject_voucher(voucher_id, note)

        logger.info(f'Voucher #{voucher_id} rejected from form_submission #{submission_id}')
    except Exception as e:
        logger.error(f'Voucher rejection failed for form_submission #{submission_id}: {e}', exc_info=True)


def _create_voucher_from_submission_legacy(submission_id, sub_repo):
    """Legacy: create + activate a voucher for old submissions without linked voucher_id."""
    try:
        sub, form = _is_voucher_submission(submission_id, sub_repo)
        if not sub:
            return

        answers = sub.get('answers') or {}
        fields = _parse_voucher_fields(answers)

        from accounting.vouchers.repositories import VoucherRepository
        repo = VoucherRepository()
        voucher = repo.create(
            company_id=_resolve_voucher_company(sub, form),
            issued_by_user_id=sub.get('respondent_user_id') or form.get('owner_id'),
            client_name=str(answers.get('f_client_name', '')).strip(),
            contract_number=str(answers.get('f_contract_number', '')).strip(),
            car_vin=str(answers.get('f_car_vin', '')).strip().upper(),
            validity_months=fields['validity_months'],
            voucher_type=fields['voucher_type'],
            value_lei=fields['value_lei'],
            discount_code=fields['discount_code'],
            discount_percentage=fields['discount_percentage'],
            service_items=fields['service_items'],
            notes=str(answers.get('f_notes', '')).strip() or None,
            client_email=str(answers.get('f_client_email', '')).strip() or None,
        )

        from accounting.vouchers.services import VoucherService
        VoucherService().activate_voucher(voucher['id'])

        logger.info(f'Voucher {voucher["voucher_code"]} created (legacy) from form_submission #{submission_id}')
    except Exception as e:
        logger.error(f'Legacy voucher creation failed for form_submission #{submission_id}: {e}', exc_info=True)
