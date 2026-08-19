"""Requester-scoped cancel/modify actions for leave-permit submissions."""
import logging
logger = logging.getLogger('jarvis.connecteam.leave_permit_actions')

def _get_submission(submission_id):
    from forms.repositories import SubmissionRepository
    return SubmissionRepository().get_by_id(submission_id)

def _pending_request_id(submission_id):
    from core.approvals.repositories.request_repo import RequestRepository
    return RequestRepository().get_pending_for_entity('form_submission', submission_id)

def _engine_cancel(request_id, user_id, reason=None):
    from core.approvals.engine import ApprovalEngine
    return ApprovalEngine().cancel(request_id, user_id, reason=(reason or 'withdrawn'))

def _set_status(submission_id, status):
    from forms.repositories import SubmissionRepository
    return SubmissionRepository().update_status(submission_id, status)

def _open_cancellation_approval(sub, user_id, reason=None):
    """Reuse the form_submission flow with a context.cancellation flag; the manager
    is the same approver that granted the leave. The requester's motive is stored on
    the context so the manager sees why the cancellation is requested."""
    from core.approvals.engine import ApprovalEngine
    from accounting.vouchers.services.voucher_service import VoucherService
    approver = VoucherService().resolve_approver(user_id, sub.get('company_id'), None)
    approver_id = approver['id'] if approver else None
    ctx = {
        'cancellation': True,
        'cancellation_reason': (reason or '').strip(),
        'title': f'Anulare bilet de invoire #{sub["id"]}',
        'approver_user_id': approver_id,
        'stakeholder_approver_ids': [approver_id] if approver_id else [],
        'notify_on_approve': [user_id], 'notify_on_reject': [user_id],
    }
    ApprovalEngine().submit(entity_type='form_submission', entity_id=sub['id'],
                            context=ctx, requested_by=user_id)

def cancel_leave_permit(submission_id, user_id, reason=None):
    sub = _get_submission(submission_id)
    if not sub:
        raise ValueError('Submission not found')
    if sub.get('respondent_user_id') != user_id:
        raise PermissionError('Not your leave request')
    if sub.get('status') in ('cancelled', 'rejected', 'cancellation_pending'):
        raise ValueError(f"Cannot cancel a request in state {sub.get('status')}")
    pending = _pending_request_id(submission_id)
    if pending:
        _engine_cancel(pending, user_id, reason)        # self-withdraw
        return {'status': 'cancelled'}
    if sub.get('status') == 'approved':
        _open_cancellation_approval(sub, user_id, reason)   # needs manager approval
        _set_status(submission_id, 'cancellation_pending')
        return {'status': 'cancellation_pending'}
    raise ValueError(f"Cannot cancel a request in state {sub.get('status')}")

def update_leave_permit(submission_id, user_id, answers):
    sub = _get_submission(submission_id)
    if not sub:
        raise ValueError('Submission not found')
    if sub.get('respondent_user_id') != user_id:
        raise PermissionError('Not your leave request')
    if not _pending_request_id(submission_id):
        raise ValueError('Only a pending request can be modified')
    from forms.services.form_service import FormService
    svc = FormService()
    validated = svc.validate_and_normalize_leave_answers(user_id, answers)  # Task 6b
    # Merge over the stored answers so fields the edit form doesn't resend
    # (e.g. an original destination) are preserved rather than wiped.
    merged = {**(sub.get('answers') or {}), **validated}
    from forms.repositories import SubmissionRepository
    SubmissionRepository().update_answers(submission_id, merged)
    return {'submission_id': submission_id}


def get_leave_permit(submission_id, user_id):
    """Full stored answers for the edit-form prefill (requester-scoped) — includes
    f_bi_notes / f_bi_second_approver which the leave-list row does not carry, so
    a modify no longer silently drops them."""
    sub = _get_submission(submission_id)
    if not sub:
        raise ValueError('Submission not found')
    if sub.get('respondent_user_id') != user_id:
        raise PermissionError('Not your leave request')
    answers = sub.get('answers') or {}
    keys = ('f_bi_leave_date', 'f_bi_start_time', 'f_bi_duration_hours', 'f_bi_reason',
            'f_bi_second_approver', 'f_bi_notes')
    return {'status': sub.get('status'), 'answers': {k: answers.get(k) for k in keys}}
