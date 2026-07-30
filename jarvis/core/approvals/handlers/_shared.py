import logging
import os
from core.notifications.notify import notify_user, notify_users
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.handlers')

_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://jarvis.autoworld.ro')


def _get_user_email(user_id) -> tuple:
    """Return (name, email) for a user_id, or (None, None) on failure."""
    if not user_id:
        return None, None
    try:
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


def _entity_link(entity_type, entity_id):
    """Get the frontend link for an entity."""
    if entity_type == 'mkt_project' and entity_id:
        return f'/app/marketing/projects/{entity_id}'
    if entity_type == 'invoice' and entity_id:
        return f'/app/accounting/invoices/{entity_id}'
    if entity_type == 'invoice':
        return '/app/accounting'
    if entity_type == 'form_submission' and entity_id:
        return '/app/approvals'
    if entity_type == 'carpark_price_change':
        return '/app/carpark/pricing-rules'
    if entity_type == 'leave_permit_conversion':
        return '/app/hr?tab=leave-permits'
    if entity_type == 'voucher':
        return '/app/accounting/vouchers'
    return '/app/approvals'


def _approval_deeplink(entity_type, entity_id, request_id):
    """Notification target: form submissions route through the app-or-web landing."""
    if entity_type == 'form_submission' and request_id:
        return f'/go/approval/{request_id}'
    return _entity_link(entity_type, entity_id)


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
