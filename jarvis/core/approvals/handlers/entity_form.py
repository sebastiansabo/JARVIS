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
        SubmissionRepository().update_status(entity_id, 'approved')
        logger.info(f'Form submission #{entity_id} status set to approved via approval hook')
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
