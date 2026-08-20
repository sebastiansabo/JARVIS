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
    from core.organization.manager_utils import get_direct_manager
    approver = get_direct_manager(user_id)   # Sincron organigram (aligns leave approval)
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


# ── HR-scoped actions (admin Leave-Permits tab) ──
# Unlike the requester-scoped helpers above, these are gated only by the HR/admin
# route decorator (@admin_required) — no ownership or pending-state check. HR can
# edit the LEAVE DETAILS (date/start/end/reason) of any leave and soft-delete
# (archive) / restore it, across both storage backends. Status/approval state is
# never touched. The per-source DB calls are isolated in thin helpers so the
# branching + normalization logic is unit-testable without a database.

_ALLOWED_SOURCES = ('jarvis', 'connecteam')


def _hr_get_jarvis(entity_id):
    from forms.repositories import SubmissionRepository
    return SubmissionRepository().get_by_id(entity_id)

def _hr_update_jarvis_answers(entity_id, answers):
    from forms.repositories import SubmissionRepository
    return SubmissionRepository().update_answers(entity_id, answers)

def _hr_archive_jarvis(entity_id, actor_id, archived):
    from forms.repositories import SubmissionRepository
    return SubmissionRepository().set_archived(entity_id, actor_id if archived else None, archived)

def _hr_get_connecteam(entity_id):
    from core.connectors.connecteam.repositories.connecteam_repository import ConnecteamRepository
    return ConnecteamRepository().get_submission_by_id(entity_id)

def _hr_update_connecteam_fields(entity_id, fields):
    from core.connectors.connecteam.repositories.connecteam_repository import ConnecteamRepository
    return ConnecteamRepository().update_leave_fields(entity_id, fields)

def _hr_archive_connecteam(entity_id, actor_id, archived):
    from core.connectors.connecteam.repositories.connecteam_repository import ConnecteamRepository
    return ConnecteamRepository().set_archived(entity_id, actor_id if archived else None, archived)


def _normalize_hr_edit(fields):
    """Validate + normalize an HR leave-detail edit.

    Returns (leave_date, start_hm, end_hm, hours, reason). Raises ValueError with
    a user-facing (Romanian) message on bad input. Hours are derived from the
    start/end span so JARVIS (duration-based) and Connecteam (end-time-based)
    rows stay consistent under the same HR form.
    """
    from datetime import datetime
    from core.connectors.connecteam.services.leave_schedule import parse_hm
    fields = fields or {}
    date_s = str(fields.get('leave_date') or '').strip()
    reason = str(fields.get('leave_reason') or '').strip()
    try:
        datetime.strptime(date_s, '%Y-%m-%d')
    except ValueError:
        raise ValueError('Data invalidă (format AAAA-LL-ZZ).')
    start_m = parse_hm(str(fields.get('leave_start_time') or ''))
    end_m = parse_hm(str(fields.get('leave_end_time') or ''))
    if start_m is None or end_m is None:
        raise ValueError('Ora de început/sfârșit invalidă (HH:MM).')
    if end_m <= start_m:
        raise ValueError('Ora de sfârșit trebuie să fie după ora de început.')
    hours = round((end_m - start_m) / 60.0, 2)
    return (date_s, f'{start_m // 60:02d}:{start_m % 60:02d}',
            f'{end_m // 60:02d}:{end_m % 60:02d}', hours, reason)


def hr_update_leave(source, entity_id, fields):
    """HR override edit of leave DETAILS (date/start/end/reason) — status untouched.

    'jarvis'     → merges the normalized details into the answers JSON (untouched
                   keys like notes / second approver are preserved).
    'connecteam' → updates the flat leave columns.
    Raises ValueError on unknown source / bad input, LookupError if not found.
    """
    if source not in _ALLOWED_SOURCES:
        raise ValueError('Sursă necunoscută')
    date_s, start_hm, end_hm, hours, reason = _normalize_hr_edit(fields)
    if source == 'jarvis':
        sub = _hr_get_jarvis(entity_id)
        if not sub:
            raise LookupError('Submission not found')
        answers = dict(sub.get('answers') or {})
        answers.update({
            'f_bi_leave_date': date_s,
            'f_bi_start_time': start_hm,
            'f_bi_end_time': end_hm,
            'f_bi_duration_hours': hours,
            'f_bi_hours': hours,
            'f_bi_reason': reason,
        })
        _hr_update_jarvis_answers(entity_id, answers)
    else:
        if not _hr_get_connecteam(entity_id):
            raise LookupError('Submission not found')
        _hr_update_connecteam_fields(entity_id, {
            'leave_date': date_s, 'leave_start_time': start_hm,
            'leave_end_time': end_hm, 'leave_hours': hours, 'leave_reason': reason,
        })
    return {'source': source, 'id': entity_id}


def hr_set_archived(source, entity_id, actor_id, archived):
    """Soft-delete (archived=True) or restore (archived=False) a leave, either source.

    Archive is a pure visibility toggle — it does not cancel a pending approval.
    Raises ValueError on unknown source, LookupError if not found.
    """
    if source not in _ALLOWED_SOURCES:
        raise ValueError('Sursă necunoscută')
    if source == 'jarvis':
        if not _hr_get_jarvis(entity_id):
            raise LookupError('Submission not found')
        _hr_archive_jarvis(entity_id, actor_id, archived)
    else:
        if not _hr_get_connecteam(entity_id):
            raise LookupError('Submission not found')
        _hr_archive_connecteam(entity_id, actor_id, archived)
    return {'source': source, 'id': entity_id, 'archived': archived}
