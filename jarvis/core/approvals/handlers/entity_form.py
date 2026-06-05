"""form_submission entity handlers."""
import logging
from ._shared import _notify_form_submission_users, _send_approval_email, _approval_email_base, _APP_BASE_URL

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_form')


def handle_submitted(entity_id, ctx):
    """Set form_submission to pending_approval on submit."""
    try:
        from forms.repositories import SubmissionRepository
        SubmissionRepository().update_status(entity_id, 'pending_approval')
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
        SubmissionRepository().update_status(entity_id, 'rejected')
        logger.info(f'Form submission #{entity_id} status set to rejected via approval hook')
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
