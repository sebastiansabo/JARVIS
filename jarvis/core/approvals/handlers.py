"""Approval event handlers — fires in-app notifications + emails + entity status changes.

Registered at app startup via register_approval_hooks().
"""

import logging
import os
from core.notifications.notify import notify_user, notify_users

logger = logging.getLogger('jarvis.core.approvals.handlers')

_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://jarvis-mkt-t6fk7.ondigitalocean.app')


# ── Email helpers ──

def _get_user_email(user_id) -> tuple:
    """Return (name, email) for a user_id, or (None, None) on failure."""
    if not user_id:
        return None, None
    try:
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT name, email FROM users WHERE id = %s', (user_id,))
            row = cursor.fetchone()
            if row:
                return row['name'], row['email']
        finally:
            release_db(conn)
    except Exception as e:
        logger.error(f'Failed to get user email for {user_id}: {e}')
    return None, None


def _get_users_email(user_ids: list) -> list:
    """Return list of (name, email) tuples for a list of user_ids."""
    if not user_ids:
        return []
    try:
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(user_ids))
            cursor.execute(f'SELECT name, email FROM users WHERE id IN ({placeholders})', user_ids)
            return [(row['name'], row['email']) for row in cursor.fetchall() if row['email']]
        finally:
            release_db(conn)
    except Exception as e:
        logger.error(f'Failed to get user emails: {e}')
    return []


def _send_approval_email(to_email, subject, html_body):
    """Send an approval email if SMTP is configured. Silently skips if not."""
    try:
        from core.services.notification_service import send_email, is_smtp_configured
        if not is_smtp_configured():
            logger.debug('SMTP not configured — skipping approval email')
            return
        success, err = send_email(to_email, subject, html_body, skip_global_cc=True)
        if not success:
            logger.warning(f'Approval email to {to_email} failed: {err}')
        else:
            logger.info(f'Approval email sent to {to_email}: {subject}')
    except Exception as e:
        logger.error(f'Failed to send approval email to {to_email}: {e}')


def _approval_email_base(title: str, body_html: str, cta_url: str, cta_label: str) -> str:
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 30px 0; margin: 0;">
      <div style="max-width: 560px; margin: 0 auto; background: #fff; border-radius: 8px;
                  border: 1px solid #e0e0e0; overflow: hidden;">
        <div style="background: #1a1a2e; padding: 20px 28px;">
          <span style="color: #fff; font-size: 18px; font-weight: bold; letter-spacing: 1px;">JARVIS</span>
          <span style="color: #aaa; font-size: 13px; margin-left: 10px;">Approvals</span>
        </div>
        <div style="padding: 28px;">
          <h2 style="margin: 0 0 16px; font-size: 18px; color: #111;">{title}</h2>
          {body_html}
          <div style="margin-top: 28px;">
            <a href="{cta_url}" style="display: inline-block; background: #4f46e5; color: #fff;
               text-decoration: none; padding: 10px 22px; border-radius: 6px; font-size: 14px;
               font-weight: bold;">{cta_label}</a>
          </div>
        </div>
        <div style="padding: 16px 28px; background: #f9f9f9; border-top: 1px solid #e0e0e0;
                    font-size: 11px; color: #999;">
          Aceasta este o notificare automata din sistemul JARVIS. Va rugam sa nu raspundeti la
          acest email.
        </div>
      </div>
    </body>
    </html>
    """


def register_approval_hooks():
    """Register all approval event handlers. Call once at app startup."""
    from core.approvals.hooks import on

    on('approval.submitted', _on_submitted)
    on('approval.approved', _on_approved)
    on('approval.rejected', _on_rejected)
    on('approval.returned', _on_returned)
    on('approval.step_advanced', _on_step_advanced)
    on('approval.reminder', _on_reminder)

    logger.info('Approval notification hooks registered')


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
        try:
            from forms.repositories import SubmissionRepository
            SubmissionRepository().update_status(entity_id, 'pending_approval')
        except Exception as e:
            logger.error(f'Failed to set form_submission pending_approval on submit: {e}')

    # Ensure mkt_project status is pending_approval (covers resubmit path)
    if entity_type == 'mkt_project' and entity_id:
        try:
            from marketing.repositories import ProjectRepository
            ProjectRepository().update_status(entity_id, 'pending_approval')
        except Exception as e:
            logger.error(f'Failed to set mkt_project pending_approval on submit: {e}')

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            f'New approval request: {entity_type} #{entity_id}',
            message=f'Flow: {flow_name}. Please review and approve.',
            link=_entity_link(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )
        # Email approvers
        link = _entity_link(entity_type, entity_id)
        for name, email in _get_users_email(approver_ids):
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
                _approval_email_base(
                    f'Cerere de aprobare nouă',
                    body,
                    f'{_APP_BASE_URL}{link}',
                    'Vezi cererea',
                ),
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
            f'{entity_type.replace("_", " ").title()} #{entity_id} approved',
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

    # Auto-update form_submission status to 'approved'
    if entity_type == 'form_submission' and entity_id:
        try:
            from forms.repositories import SubmissionRepository
            SubmissionRepository().update_status(entity_id, 'approved')
            logger.info(f'Form submission #{entity_id} status set to approved via approval hook')
        except Exception as e:
            logger.error(f'Failed to update form_submission status on approval: {e}')
        # Email users in notify_on_approve + optionally respondent
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

    # Auto-update invoice status to 'approved'
    if entity_type == 'invoice' and entity_id:
        try:
            from accounting.invoices.repositories.invoice_repository import InvoiceRepository
            InvoiceRepository().update(entity_id, status='approved')
            logger.info(f'Invoice #{entity_id} status set to approved via approval hook')
        except Exception as e:
            logger.error(f'Failed to update invoice status on approval: {e}')

    # Auto-update marketing project status to 'approved' + approve budget lines
    if entity_type == 'mkt_project' and entity_id:
        try:
            from marketing.repositories import ProjectRepository, ActivityRepository
            ProjectRepository().update_status(entity_id, 'approved')
            from database import get_db, get_cursor, release_db
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('''
                    UPDATE mkt_budget_lines
                    SET approved_amount = planned_amount, status = 'approved', updated_at = NOW()
                    WHERE project_id = %s AND status = 'draft'
                ''', (entity_id,))
                conn.commit()
            finally:
                release_db(conn)
            ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                     details={'decision': 'approved'})
            logger.info(f'Marketing project #{entity_id} approved via approval hook')
        except Exception as e:
            logger.error(f'Failed to update mkt_project status on approval: {e}')

    # Apply carpark price changes on approval
    if entity_type == 'carpark_price_change' and entity_id:
        try:
            from carpark.repositories.pricing_repository import PricingRepository
            from carpark.repositories.vehicle_repository import VehicleRepository
            pricing_repo = PricingRepository()
            vehicle_repo = VehicleRepository()

            changes = pricing_repo.get_pending_changes(approval_request_id=request_id, status='pending')
            for ch in changes:
                vehicle_repo.update(ch['vehicle_id'], {
                    'current_price': float(ch['new_price'])
                })
                pricing_repo.log_price_change(
                    ch['vehicle_id'],
                    float(ch['old_price']),
                    float(ch['new_price']),
                    f'approved:rule#{entity_id}',
                    rule_id=entity_id,
                    changed_by=requester_id,
                )
            pricing_repo.update_pending_status(request_id, 'approved', applied_by=requester_id)
            logger.info(f'CarPark price changes approved for rule #{entity_id}: {len(changes)} vehicles updated')
        except Exception as e:
            logger.error(f'Failed to apply carpark price changes on approval: {e}', exc_info=True)

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
            f'{entity_type.replace("_", " ").title()} #{entity_id} rejected',
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

    # Update form_submission status to rejected
    if entity_type == 'form_submission' and entity_id:
        try:
            from forms.repositories import SubmissionRepository
            SubmissionRepository().update_status(entity_id, 'rejected')
            logger.info(f'Form submission #{entity_id} status set to rejected via approval hook')
        except Exception as e:
            logger.error(f'Failed to update form_submission status on rejection: {e}')
        # Email users in notify_on_reject + optionally respondent
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

    # Mark carpark pending price changes as rejected
    if entity_type == 'carpark_price_change' and entity_id:
        try:
            from carpark.repositories.pricing_repository import PricingRepository
            PricingRepository().update_pending_status(request_id, 'rejected')
            logger.info(f'CarPark price changes rejected for rule #{entity_id}')
        except Exception as e:
            logger.error(f'Failed to reject carpark price changes: {e}', exc_info=True)

    # Revert marketing project to draft on rejection
    if entity_type == 'mkt_project' and entity_id:
        try:
            from marketing.repositories import ProjectRepository, ActivityRepository
            ProjectRepository().update_status(entity_id, 'draft')
            ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                     details={'decision': 'rejected'})
        except Exception as e:
            logger.error(f'Failed to revert mkt_project status on rejection: {e}')


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
            f'{entity_type.replace("_", " ").title()} #{entity_id} returned',
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
        try:
            from marketing.repositories import ProjectRepository, ActivityRepository
            ProjectRepository().update_status(entity_id, 'draft')
            ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                     details={'decision': 'returned', 'comment': comment})
        except Exception as e:
            logger.error(f'Failed to revert mkt_project status on return: {e}')


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
            f'Approval request awaiting your review',
            message=f'{entity_type.replace("_", " ").title()} #{entity_id} — Step: {step_name}',
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

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            'Reminder: Approval request pending your decision',
            link='/app/approvals',
            type='approval',
        )


# ── Form submission notification helper ──

def _notify_form_submission_users(ctx: dict, config_key: str, title: str, event: str):
    """Email users listed in approval_config for form_submission events.

    config_key: one of 'notify_on_submit', 'notify_on_approve', 'notify_on_reject'
    event: 'submitted', 'approved', 'rejected' — used for email copy
    """
    user_ids = ctx.get(config_key, [])
    if not user_ids:
        return
    try:
        form_name = ctx.get('form_name', title)
        link = f'/app/forms'
        event_labels = {
            'submitted': ('Trimitere nouă', 'a fost trimis', '#2563eb'),
            'approved': ('Aprobat', 'a fost aprobat', '#16a34a'),
            'rejected': ('Respins', 'a fost respins', '#dc2626'),
        }
        label, verb, color = event_labels.get(event, ('Notificare', '', '#555'))

        for name, email in _get_users_email(user_ids):
            body = f"""
            <p>Buna ziua {name},</p>
            <p>Formularul <strong>{form_name}</strong> {verb}.</p>
            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;width:40%;">Formular</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{form_name}</td></tr>
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Respondent</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;">{ctx.get('respondent_name') or ctx.get('respondent_email') or 'Anonim'}</td></tr>
              <tr><td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #ddd;">Status</td>
                  <td style="padding:8px 12px;border:1px solid #ddd;color:{color};font-weight:bold;">{label}</td></tr>
            </table>
            """
            _send_approval_email(
                email,
                f'{label}: {form_name}',
                _approval_email_base(f'{label} — {form_name}', body,
                    f'{_APP_BASE_URL}{link}', 'Vezi în JARVIS'),
            )
    except Exception as e:
        logger.error(f'Failed to send form_submission {event} notifications: {e}')


# ── Helpers ──


def _entity_link(entity_type, entity_id):
    """Get the frontend link for an entity."""
    if entity_type == 'mkt_project' and entity_id:
        return f'/app/marketing/projects/{entity_id}'
    if entity_type == 'invoice':
        return '/app/accounting'
    if entity_type == 'form_submission' and entity_id:
        return '/app/forms'
    if entity_type == 'carpark_price_change':
        return '/app/carpark/pricing-rules'
    return '/app/approvals'


def _get_requester(request_id):
    """Get the user_id of who submitted the request."""
    try:
        from core.approvals.repositories import RequestRepository
        req = RequestRepository().get_by_id(request_id)
        return req['requested_by'] if req else None
    except Exception as e:
        logger.error(f'Failed to get requester for request {request_id}: {e}')
        return None


def _get_request(request_id) -> dict:
    """Return the full request row (includes context_snapshot). Empty dict on failure."""
    try:
        from core.approvals.repositories import RequestRepository
        req = RequestRepository().get_by_id(request_id)
        return dict(req) if req else {}
    except Exception as e:
        logger.error(f'Failed to get request {request_id}: {e}')
        return {}


def _get_current_step_approvers(request_id):
    """Get user IDs of approvers for the current step of a request."""
    try:
        from core.approvals.repositories import RequestRepository, FlowRepository
        from database import get_db, get_cursor, release_db

        req = RequestRepository().get_by_id(request_id)
        if not req or not req.get('current_step_id'):
            return []

        step = FlowRepository().get_step_by_id(req['current_step_id'])
        if not step:
            return []

        approver_type = step.get('approver_type', '')

        if approver_type == 'context_approver':
            ctx = req.get('context_snapshot') or {}
            stakeholder_ids = ctx.get('stakeholder_approver_ids', [])
            if stakeholder_ids:
                return stakeholder_ids
            single_id = ctx.get('approver_user_id')
            return [int(single_id)] if single_id else []

        if approver_type == 'specific_user' and step.get('approver_user_id'):
            return [step['approver_user_id']]

        if approver_type == 'role' and step.get('approver_role_name'):
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('''
                    SELECT u.id FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE r.name = %s AND u.is_active = TRUE
                ''', (step['approver_role_name'],))
                return [row['id'] for row in cursor.fetchall()]
            finally:
                release_db(conn)

        if approver_type == 'department_manager':
            # Would need entity context to resolve department — skip for now
            return []

        return []
    except Exception as e:
        logger.error(f'Failed to get approvers for request {request_id}: {e}')
        return []
