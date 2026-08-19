"""Approval event handlers — orchestrates notifications and entity status updates."""
import logging
from ._shared import (
    _get_request, _get_requester, _get_current_step_approvers,
    _get_user_email, _get_users_email, _send_approval_email, _approval_email_base,
    _entity_link, _approval_deeplink, _notify_form_submission_users, _APP_BASE_URL,
)
from . import entity_form, entity_marketing, entity_invoice, entity_carpark, entity_leave_permit_conversion, entity_voucher
from core.notifications.notify import notify_user, notify_users, notify_with_push

logger = logging.getLogger('jarvis.core.approvals.handlers')


def _on_submitted(payload):
    """Notify step 1 approvers that a new request needs their attention."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    flow_name = payload.get('flow_name', '')
    req = _get_request(request_id)
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'

    # Set form_submission status to pending_approval
    if entity_type == 'form_submission' and entity_id:
        entity_form.handle_submitted(entity_id, ctx)

    # Ensure mkt_project status is pending_approval (covers resubmit path)
    if entity_type == 'mkt_project' and entity_id:
        entity_marketing.handle_submitted(entity_id)

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        # Form submissions route through the app-or-web landing; the push data
        # carries the deep-link so tapping the notification opens the app.
        link = _approval_deeplink(entity_type, entity_id, request_id)
        notify_with_push(
            approver_ids,
            f'New approval request: {project_title}',
            message='Please review and approve.',
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
            push_data={'type': 'approval', 'request_id': str(request_id),
                       'entity_type': entity_type, 'link': link},
        )
        # Email approvers. Leave permits get a rich, actionable email (full summary
        # + one-tap Aprobă/Respinge); everything else keeps the generic notice.
        leave = _leave_summary_for_submission(entity_type, entity_id)
        for uid in approver_ids:
            name, email = _get_user_email(uid)
            if not email:
                continue
            if leave:
                body = _leave_notify_body(name, leave, request_id, uid)
            else:
                body = f"""
                <p>Buna ziua {name},</p>
                <p>O cerere noua de aprobare asteapta decizia dumneavoastra:</p>
                <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                  <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                      <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
                  <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Flow</td>
                      <td style="padding:8px 12px;border:1px solid #ddd;">{flow_name}</td></tr>
                </table>
                <p style="color:#555;font-size:13px;">Va rugam sa accesati JARVIS pentru a revizui si lua o decizie.</p>
                """
            _send_approval_email(
                email,
                f'Cerere de aprobare: {project_title}',
                _approval_email_base('Cerere de aprobare nouă', body,
                    f'{_APP_BASE_URL}{link}', 'Vezi cererea'),
            )

    # Form submission: email users in notify_on_submit from approval_config
    if entity_type == 'form_submission':
        _notify_form_submission_users(ctx, 'notify_on_submit', project_title, 'submitted')


def _on_approved(payload):
    """Notify requester their request was approved. Update entity status."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    auto = payload.get('auto_approved', False)
    req = _get_request(request_id)
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'

    requester_id = _get_requester(request_id)
    if requester_id:
        msg = 'Auto-approved' if auto else 'All approval steps completed'
        notify_user(
            requester_id,
            f'{project_title} — approved',
            message=msg,
            link=_entity_link(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        name, email = _get_user_email(requester_id)
        if email:
            link = _entity_link(entity_type, entity_id)
            body = f"""
            <p>Buna ziua {name},</p>
            <p>Cererea dumneavoastra de aprobare a fost <strong style="color:#16a34a;">aprobata</strong>.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Status</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;color:#16a34a;font-weight:bold;">{'Auto-aprobat' if auto else 'Aprobat — toate etapele finalizate'}</td></tr>
            </table>
            """
            _send_approval_email(
                email,
                f'Aprobat: {project_title}',
                _approval_email_base('Cererea a fost aprobată ✓', body,
                    f'{_APP_BASE_URL}{link}', 'Vezi proiectul'),
            )

    # form_submission: route cancellation-approval requests separately from
    # normal submission approvals.
    if entity_type == 'form_submission' and entity_id:
        if ctx.get('cancellation'):
            entity_form.handle_cancellation_approved(entity_id, ctx)
        else:
            # Notify the requester's direct manager (scheduler) so they can update
            # the schedule — unless that manager is the one who just approved it.
            _maybe_notify_leave_scheduler(request_id, entity_id, ctx)
            # Auto-update form_submission status to 'approved'
            entity_form.handle_approved(entity_id, ctx)

    # Auto-update invoice status to 'approved'
    if entity_type == 'invoice' and entity_id:
        entity_invoice.handle_approved(entity_id)

    # Auto-update marketing project status to 'approved' + approve budget lines
    if entity_type == 'mkt_project' and entity_id:
        entity_marketing.handle_approved(entity_id, request_id, requester_id)

    # Apply carpark price changes on approval
    if entity_type == 'carpark_price_change' and entity_id:
        entity_carpark.handle_approved(entity_id, request_id, requester_id)

    # Deduct CO days on leave permit conversion approval
    if entity_type == 'leave_permit_conversion' and entity_id:
        entity_leave_permit_conversion.handle_approved(entity_id, request_id, requester_id)

    # Activate voucher on approval
    if entity_type == 'voucher' and entity_id:
        entity_voucher.handle_approved(entity_id, request_id, requester_id)

    # Auto-create signature request if flow requires_signature
    try:
        from core.approvals.repositories import RequestRepository, FlowRepository
        req = RequestRepository().get_by_id(request_id)
        if req:
            flow = FlowRepository().get_flow_by_id(req['flow_id'])
            if flow and flow.get('requires_signature'):
                from core.signatures.services import SignatureService
                SignatureService().request_signature(
                    document_type=entity_type,
                    document_id=entity_id,
                    signed_by=req['requested_by'],
                    callback_url=_entity_link(entity_type, entity_id),
                )
                logger.info(
                    f'Signature request created for {entity_type} #{entity_id} '
                    f'(flow requires_signature=true)'
                )
    except Exception as e:
        logger.error(f'Failed to create signature request on approval: {e}')


def _approved_decider_ids(decisions):
    return {d['decided_by'] for d in (decisions or []) if d.get('decision') == 'approved'}


def _load_leave_submission(submission_id):
    from core.base_repository import BaseRepository
    return BaseRepository().query_one('''
        SELECT fs.answers, fs.respondent_user_id, fs.company_id,
               f.slug, u.name AS requester_name
        FROM form_submissions fs
        JOIN forms f ON f.id = fs.form_id
        LEFT JOIN users u ON u.id = fs.respondent_user_id
        WHERE fs.id = %s''', (submission_id,))


def _leave_summary_for_submission(entity_type, entity_id):
    """Leave summary dict for a bilet-de-invoire submission, else None."""
    if entity_type == 'form_submission' and entity_id:
        from .leave_summary import build_leave_summary
        return build_leave_summary(entity_id)
    return None


def _leave_notify_body(approver_name, leave, request_id, approver_id):
    """Actionable approver email body: leave summary + signed one-tap decide links.
    Falls back to a button-less summary if there's no app context to sign tokens."""
    from .leave_email import leave_approval_email_body
    secret = None
    try:
        from flask import current_app
        secret = current_app.secret_key
    except Exception:
        secret = None
    if not secret:
        return leave_approval_email_body(approver_name, leave, '', '')
    from core.approvals.action_token import make_action_token

    def _url(act):
        tok = make_action_token(request_id, approver_id, act, secret)
        return f'{_APP_BASE_URL}/go/approval/act?token={tok}'
    return leave_approval_email_body(approver_name, leave, _url('approve'), _url('reject'))


def _resolve_manager(user_id, company_id):
    from accounting.vouchers.services import VoucherService
    return VoucherService().resolve_approver(user_id, company_id or 0)


def _load_approved_deciders(request_id):
    from core.approvals.repositories import DecisionRepository
    return _approved_decider_ids(DecisionRepository().get_decisions_for_request(request_id))


def _maybe_notify_leave_scheduler(request_id, submission_id, ctx):
    """Notify the employee's direct manager (scheduler) that a leave was approved,
    unless that manager is the person who just approved it."""
    try:
        row = _load_leave_submission(submission_id)
        if not row or row.get('slug') != 'bilet-de-invoire':
            return
        requester_id = row.get('respondent_user_id')
        if not requester_id:
            return
        manager = _resolve_manager(requester_id, row.get('company_id'))
        if not manager:
            return
        manager_id = manager['id']
        if manager_id in _load_approved_deciders(request_id):
            return  # dedup: they already approved, they know
        a = row.get('answers') or {}
        name = row.get('requester_name') or 'Un angajat'
        msg = (f"{name} va lipsi {a.get('f_bi_leave_date','')} "
               f"{a.get('f_bi_start_time','')}–{a.get('f_bi_end_time','')} "
               f"({a.get('f_bi_hours','')}h). Actualizează programul.")
        title = 'Învoire aprobată — actualizează programul'
        link = '/app/hub?module=hr&hrtab=leave-permits'
        notify_user(manager_id, title, message=msg, link=link,
                    entity_type='form_submission', entity_id=submission_id, type='info')
        _, email = _get_user_email(manager_id)
        if email:
            _send_approval_email(email, title,
                _approval_email_base('Învoire aprobată', f'<p>{msg}</p>',
                                     f'{_APP_BASE_URL}{link}', 'Deschide programul'))
    except Exception as e:
        logger.warning('scheduler notify failed for submission %s: %s', submission_id, e)


def _on_rejected(payload):
    """Notify requester their request was rejected."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    note = payload.get('resolution_note', '')
    req = _get_request(request_id)
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'

    requester_id = _get_requester(request_id)
    if requester_id:
        notify_user(
            requester_id,
            f'{project_title} — rejected',
            message=note or 'Your request was rejected.',
            link=_entity_link(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        name, email = _get_user_email(requester_id)
        if email:
            link = _entity_link(entity_type, entity_id)
            note_row = f"""<tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Motiv</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{note}</td></tr>""" if note else ''
            body = f"""
            <p>Buna ziua {name},</p>
            <p>Cererea dumneavoastra de aprobare a fost <strong style="color:#dc2626;">respinsa</strong>.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
              {note_row}
            </table>
            """
            _send_approval_email(
                email,
                f'Respins: {project_title}',
                _approval_email_base('Cererea a fost respinsă', body,
                    f'{_APP_BASE_URL}{link}', 'Vezi proiectul'),
            )

    # form_submission: route cancellation-approval requests separately from
    # normal submission rejections.
    if entity_type == 'form_submission' and entity_id:
        if ctx.get('cancellation'):
            entity_form.handle_cancellation_rejected(entity_id, ctx)
        else:
            entity_form.handle_rejected(entity_id, ctx, note)

    # Mark carpark pending price changes as rejected
    if entity_type == 'carpark_price_change' and entity_id:
        entity_carpark.handle_rejected(entity_id, request_id)

    # Revert marketing project to draft on rejection
    if entity_type == 'mkt_project' and entity_id:
        entity_marketing.handle_rejected(entity_id)

    # Reject leave permit conversion
    if entity_type == 'leave_permit_conversion' and entity_id:
        entity_leave_permit_conversion.handle_rejected(entity_id, request_id)

    # Reject voucher
    if entity_type == 'voucher' and entity_id:
        entity_voucher.handle_rejected(entity_id, comment=note)


def _on_cancelled(payload):
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    req = _get_request(request_id)
    ctx = (req or {}).get('context_snapshot') or {}
    if entity_type == 'form_submission' and entity_id:
        entity_form.handle_cancelled(entity_id, ctx)


def _on_returned(payload):
    """Notify requester their request was returned for changes."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    comment = payload.get('comment', '')
    req = _get_request(request_id)
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'

    requester_id = _get_requester(request_id)
    if requester_id:
        notify_user(
            requester_id,
            f'{project_title} — returned',
            message=comment or 'Please review and resubmit.',
            link=_entity_link(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        name, email = _get_user_email(requester_id)
        if email:
            link = _entity_link(entity_type, entity_id)
            comment_row = f"""<tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Comentariu</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{comment}</td></tr>""" if comment else ''
            body = f"""
            <p>Buna ziua {name},</p>
            <p>Cererea dumneavoastra a fost <strong style="color:#2563eb;">returnata pentru modificari</strong>.
            Va rugam sa revizuiti si sa retrimiti.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
              {comment_row}
            </table>
            """
            _send_approval_email(
                email,
                f'Returnata pentru modificari: {project_title}',
                _approval_email_base('Cererea a fost returnată', body,
                    f'{_APP_BASE_URL}{link}', 'Revizuieste proiectul'),
            )

    # Revert marketing project to draft on return
    if entity_type == 'mkt_project' and entity_id:
        entity_marketing.handle_returned(entity_id, comment)


def _on_step_advanced(payload):
    """Notify next step approvers that a request needs their attention."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    step_name = payload.get('step_name', '')
    req = _get_request(request_id)
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            f'Approval request: {project_title}',
            message=f'Step: {step_name}. Please review and approve.',
            link=_entity_link(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        link = _entity_link(entity_type, entity_id)
        for name, email in _get_users_email(approver_ids):
            body = f"""
            <p>Buna ziua {name},</p>
            <p>O cerere de aprobare a avansat la etapa urmatoare si asteapta decizia
            dumneavoastra:</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Etapa curenta</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{step_name}</td></tr>
            </table>
            """
            _send_approval_email(
                email,
                f'Cerere in asteptare — Etapa: {step_name}',
                _approval_email_base('Cerere de aprobare în așteptare', body,
                    f'{_APP_BASE_URL}{link}', 'Revizuieste cererea'),
            )


def _on_reminder(payload):
    """Remind current step approvers about a pending request."""
    request_id = payload.get('request_id')
    req = _get_request(request_id)
    entity_type = req.get('entity_type', '')
    entity_id = req.get('entity_id')
    ctx = req.get('context_snapshot') or {}
    project_title = ctx.get('title') or f'{entity_type} #{entity_id}'
    link = _entity_link(entity_type, entity_id)

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            f'Reminder: {project_title} awaits your approval',
            message='This request has been pending for over 48 hours.',
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        for name, email in _get_users_email(approver_ids):
            body = f"""
            <p>Buna ziua {name},</p>
            <p>Aceasta este o reamintire ca urmatoarea cerere de aprobare asteapta
            decizia dumneavoastra de mai mult de <strong>48 de ore</strong>:</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Proiect</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{project_title}</td></tr>
            </table>
            <p style="color:#555;font-size:13px;">Va rugam sa accesati JARVIS pentru a revizui si lua o decizie.</p>
            """
            _send_approval_email(
                email,
                f'Reamintire: {project_title} — aprobare in asteptare',
                _approval_email_base(
                    'Reamintire — cerere de aprobare',
                    body,
                    f'{_APP_BASE_URL}{link}',
                    'Revizuieste cererea',
                ),
            )
