"""Forms Service — business logic for form operations and submissions."""

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from forms.repositories import FormRepository, SubmissionRepository

logger = logging.getLogger('jarvis.forms.service')


@dataclass
class UserContext:
    """Lightweight user context passed from route handlers."""
    user_id: int
    company: Optional[str] = None


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200


# Supported field types for validation
FIELD_TYPES = {
    'short_text', 'long_text', 'email', 'phone', 'number',
    'dropdown', 'radio', 'checkbox', 'date', 'file_upload',
    'heading', 'paragraph', 'hidden', 'signature',
}
# Display-only fields that don't produce answers
DISPLAY_ONLY_TYPES = {'heading', 'paragraph'}

# Email validation regex (RFC 5322 simplified)
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9]'
    r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)

# Max length for string fields to prevent abuse
_MAX_TEXT_LENGTH = 10_000
_MAX_SHORT_TEXT_LENGTH = 500


def _sanitize_string(value: str) -> str:
    """Sanitize a string value — escape HTML entities to prevent XSS."""
    if not isinstance(value, str):
        return value
    return html.escape(value, quote=True)


def _sanitize_answers(answers: Dict) -> Dict:
    """Sanitize all string values in the answers dict."""
    sanitized = {}
    for key, value in answers.items():
        if isinstance(value, str):
            sanitized[key] = _sanitize_string(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_string(v) if isinstance(v, str) else v for v in value]
        else:
            sanitized[key] = value
    return sanitized


class FormService:
    """Orchestrates form business logic."""

    def __init__(self):
        self.form_repo = FormRepository()
        self.submission_repo = SubmissionRepository()

    # ============== Form Lifecycle ==============

    def create_form(self, data: Dict, user: UserContext) -> ServiceResult:
        """Create a new form."""
        name = data.get('name')
        company_id = data.get('company_id')
        if not name or not company_id:
            return ServiceResult(success=False, error='name and company_id are required', status_code=400)

        form_id = self.form_repo.create(
            name=name,
            company_id=company_id,
            owner_id=data.get('owner_id', user.user_id),
            created_by=user.user_id,
            description=data.get('description'),
            schema=data.get('schema', []),
            settings=data.get('settings', {}),
            utm_config=data.get('utm_config', {}),
            branding=data.get('branding', {}),
            requires_approval=data.get('requires_approval', False),
        )
        return ServiceResult(success=True, data={'id': form_id}, status_code=201)

    def publish_form(self, form_id: int, user: UserContext) -> ServiceResult:
        """Publish a form (copies schema → published_schema)."""
        form = self.form_repo.get_by_id(form_id)
        if not form:
            return ServiceResult(success=False, error='Form not found', status_code=404)

        schema = form.get('schema', [])
        if not schema or len(schema) == 0:
            return ServiceResult(
                success=False,
                error='Cannot publish a form with no fields',
                status_code=400,
            )

        # Check at least one input field (not just headings/paragraphs)
        input_fields = [f for f in schema if f.get('type') not in DISPLAY_ONLY_TYPES]
        if not input_fields:
            return ServiceResult(
                success=False,
                error='Form must have at least one input field',
                status_code=400,
            )

        self.form_repo.publish(form_id)
        return ServiceResult(success=True, data={'version': form.get('version', 1) + 1})

    # ============== Public Submission ==============

    def submit_public(self, slug: str, answers: Dict, utm_data: Dict,
                      respondent_info: Dict, ip: Optional[str] = None) -> ServiceResult:
        """Handle a public form submission."""
        form = self.form_repo.get_by_slug(slug)
        if not form:
            return ServiceResult(success=False, error='Form not found or not published', status_code=404)

        schema = form.get('published_schema', [])

        # Check submission limit
        settings = form.get('settings', {})
        submission_limit = settings.get('submission_limit')
        if submission_limit:
            current_count = self.form_repo.count_submissions(form['id'])
            if current_count >= int(submission_limit):
                msg = settings.get('limit_message', 'This form is no longer accepting submissions.')
                return ServiceResult(success=False, error=msg, status_code=403)

        # Strip unknown answer keys — only accept keys matching schema field IDs
        known_field_ids = {f.get('id') for f in schema if f.get('id')}
        answers = {k: v for k, v in answers.items() if k in known_field_ids}

        # Validate required fields and types
        validation_error = self._validate_answers(schema, answers)
        if validation_error:
            return ServiceResult(success=False, error=validation_error, status_code=400)

        # Sanitize answers to prevent stored XSS
        answers = _sanitize_answers(answers)

        # Filter UTM data to only tracked params
        tracked_utms = form.get('utm_config', {}).get('track', [
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        ])
        filtered_utm = {k: _sanitize_string(str(v)) for k, v in utm_data.items() if k in tracked_utms}
        # Apply defaults for missing UTMs
        defaults = form.get('utm_config', {}).get('defaults', {})
        for key, default_val in defaults.items():
            if key not in filtered_utm and key in tracked_utms:
                filtered_utm[key] = _sanitize_string(str(default_val))

        # Sanitize respondent info
        sanitized_respondent = {
            'name': _sanitize_string(respondent_info.get('name') or ''),
            'email': _sanitize_string(respondent_info.get('email') or ''),
            'phone': _sanitize_string(respondent_info.get('phone') or ''),
        }

        submission_id = self.submission_repo.create(
            form_id=form['id'],
            form_version=form.get('version', 1),
            answers=answers,
            form_schema_snapshot=schema,
            source='web_public',
            company_id=form.get('company_id'),
            respondent_name=sanitized_respondent['name'] or None,
            respondent_email=sanitized_respondent['email'] or None,
            respondent_phone=sanitized_respondent['phone'] or None,
            respondent_ip=ip,
            utm_data=filtered_utm,
        )

        # Trigger approval if required
        if form.get('requires_approval'):
            self._trigger_approval(form, submission_id, sanitized_respondent)
        else:
            # Even without approval, send submit notifications
            self._send_submit_notifications(form, submission_id, sanitized_respondent)

        thank_you = settings.get('thank_you_message', 'Thank you for your submission!')
        redirect_url = settings.get('redirect_url')

        return ServiceResult(success=True, data={
            'submission_id': submission_id,
            'thank_you_message': thank_you,
            'redirect_url': redirect_url,
        }, status_code=201)

    def submit_internal(self, form_id: int, answers: Dict,
                        user: UserContext, source: str = 'web_internal') -> ServiceResult:
        """Handle an internal (authenticated) form submission."""
        form = self.form_repo.get_by_id(form_id)
        if not form:
            return ServiceResult(success=False, error='Form not found', status_code=404)

        schema = form.get('published_schema') or form.get('schema', [])

        # Strip unknown answer keys
        known_field_ids = {f.get('id') for f in schema if f.get('id')}
        answers = {k: v for k, v in answers.items() if k in known_field_ids}

        validation_error = self._validate_answers(schema, answers)
        if validation_error:
            return ServiceResult(success=False, error=validation_error, status_code=400)

        # Sanitize answers
        answers = _sanitize_answers(answers)

        submission_id = self.submission_repo.create(
            form_id=form_id,
            form_version=form.get('version', 1),
            answers=answers,
            form_schema_snapshot=schema,
            source=source,
            company_id=form.get('company_id'),
            respondent_user_id=user.user_id,
        )

        if form.get('requires_approval'):
            self._trigger_approval(form, submission_id, {'user_id': user.user_id})

        return ServiceResult(success=True, data={'submission_id': submission_id}, status_code=201)

    # ============== Approval ==============

    def trigger_approval(self, submission_id: int, user_id: int) -> ServiceResult:
        """Manually trigger approval for a submission."""
        submission = self.submission_repo.get_by_id(submission_id)
        if not submission:
            return ServiceResult(success=False, error='Submission not found', status_code=404)

        form = self.form_repo.get_by_id(submission['form_id'])
        if not form:
            return ServiceResult(success=False, error='Form not found', status_code=404)

        return self._trigger_approval(form, submission_id, {
            'user_id': user_id,
            'respondent_email': submission.get('respondent_email'),
        })

    # ============== Private Helpers ==============

    def _validate_answers(self, schema: List[Dict], answers: Dict) -> Optional[str]:
        """Validate answers against form schema. Returns error message or None."""
        if not schema:
            return None

        for field in schema:
            field_id = field.get('id')
            field_type = field.get('type')
            if not field_id or field_type in DISPLAY_ONLY_TYPES:
                continue

            is_required = field.get('required', False)
            value = answers.get(field_id)

            if is_required and (value is None or value == '' or value == []):
                label = field.get('label', field_id)
                return f'Field "{label}" is required'

            if value is not None and value != '':
                # Email validation with proper regex
                if field_type == 'email':
                    if not isinstance(value, str) or not _EMAIL_RE.match(value):
                        return f'Field "{field.get("label", field_id)}" must be a valid email address'
                    if len(value) > 254:
                        return f'Field "{field.get("label", field_id)}" exceeds maximum email length'

                # Number validation
                if field_type == 'number':
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        return f'Field "{field.get("label", field_id)}" must be a number'

                # Text length limits
                if field_type == 'short_text' and isinstance(value, str) and len(value) > _MAX_SHORT_TEXT_LENGTH:
                    return f'Field "{field.get("label", field_id)}" exceeds maximum length of {_MAX_SHORT_TEXT_LENGTH} characters'

                if field_type == 'long_text' and isinstance(value, str) and len(value) > _MAX_TEXT_LENGTH:
                    return f'Field "{field.get("label", field_id)}" exceeds maximum length of {_MAX_TEXT_LENGTH} characters'

                # Dropdown/radio — value must be one of the defined options
                if field_type in ('dropdown', 'radio') and isinstance(value, str):
                    options = field.get('options', [])
                    if options and value not in options:
                        return f'Field "{field.get("label", field_id)}" has an invalid selection'

                # Checkbox — all values must be in defined options
                if field_type == 'checkbox' and isinstance(value, list):
                    options = field.get('options', [])
                    if options:
                        for v in value:
                            if v not in options:
                                return f'Field "{field.get("label", field_id)}" has an invalid selection'

                # Signature — must be base64 image, max 500KB
                if field_type == 'signature' and isinstance(value, str):
                    if not value.startswith('data:image/'):
                        return f'Field "{field.get("label", field_id)}" must be a valid signature image'
                    if len(value) > 512_000:
                        return f'Field "{field.get("label", field_id)}" signature is too large'

        return None

    def _send_submit_notifications(self, form: Dict, submission_id: int,
                                    respondent_info: Dict):
        """Send email notifications for new submission (no approval flow)."""
        try:
            approval_config = form.get('approval_config', {})
            notify_ids = approval_config.get('notify_on_submit', [])
            if not notify_ids:
                return

            from core.services.notification_service import send_email, is_smtp_configured
            if not is_smtp_configured():
                return

            # Resolve user emails
            from database import get_db, get_cursor, release_db
            conn = get_db()
            try:
                cur = get_cursor(conn)
                placeholders = ','.join(['%s'] * len(notify_ids))
                cur.execute(f'SELECT email, name FROM users WHERE id IN ({placeholders})', notify_ids)
                users = cur.fetchall()
            finally:
                release_db(conn)

            form_name = form.get('name', 'Unknown Form')
            respondent = respondent_info.get('name') or respondent_info.get('email') or 'Anonymous'

            for user in users:
                subject = f'New submission: {form_name}'
                html = f'''<h3>New Form Submission</h3>
                <p><strong>Form:</strong> {form_name}</p>
                <p><strong>Respondent:</strong> {respondent}</p>
                <p><strong>Submission ID:</strong> {submission_id}</p>
                <p><a href="/app/forms/{form["id"]}">View Submission</a></p>'''
                send_email(user['email'], subject, html, skip_global_cc=True)
        except Exception as e:
            logger.error(f'Submit notification failed for submission {submission_id}: {e}')

    def _trigger_approval(self, form: Dict, submission_id: int,
                          respondent_info: Dict) -> ServiceResult:
        """Submit a form submission for approval via the approval engine."""
        try:
            from core.approvals.engine import ApprovalEngine
            engine = ApprovalEngine()

            approval_config = form.get('approval_config', {})

            context = {
                'form_id': form['id'],
                'form_name': form.get('name', ''),
                'submission_id': submission_id,
                'respondent_email': respondent_info.get('email', ''),
                'respondent_name': respondent_info.get('name', ''),
                'company_id': form.get('company_id'),
                'notify_on_submit': approval_config.get('notify_on_submit', []),
                'notify_on_approve': approval_config.get('notify_on_approve', []),
                'notify_on_reject': approval_config.get('notify_on_reject', []),
                'notify_respondent': approval_config.get('notify_respondent', False),
                'requires_signature': approval_config.get('requires_signature', False),
            }

            requested_by = respondent_info.get('user_id', form.get('owner_id'))
            result = engine.submit(
                entity_type='form_submission',
                entity_id=submission_id,
                context=context,
                requested_by=requested_by,
            )

            # Link approval request to submission
            request_id = result.get('request_id') if isinstance(result, dict) else result
            if request_id:
                self.submission_repo.set_approval_request(submission_id, request_id)
                self.submission_repo.update_status(submission_id, 'flagged')

            # Send submit notifications
            self._send_submit_notifications(form, submission_id, respondent_info)

            return ServiceResult(success=True, data={'approval_request_id': request_id})
        except Exception as e:
            logger.error(f'Approval trigger failed for submission {submission_id}: {e}', exc_info=True)
            return ServiceResult(success=False, error='Failed to trigger approval workflow', status_code=500)
