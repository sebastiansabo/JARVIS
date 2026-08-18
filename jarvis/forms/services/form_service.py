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
    'dropdown', 'radio', 'checkbox', 'date', 'datetime', 'file_upload',
    'heading', 'paragraph', 'hidden', 'signature',
    'crm_client', 'service_catalog', 'company_select',
    'department_select', 'user_select',
    'fp_vehicle', 'fp_client',
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
                      respondent_info: Dict, ip: Optional[str] = None,
                      user_id: Optional[int] = None) -> ServiceResult:
        """Handle a public form submission."""
        form = self.form_repo.get_by_slug(slug)
        if not form:
            return ServiceResult(success=False, error='Form not found or not published', status_code=404)

        schema = form.get('published_schema', [])

        # Block internal-only forms from public submission (allow if user is logged in)
        settings = form.get('settings', {})
        if isinstance(settings, str):
            import json as _json
            settings = _json.loads(settings)
        if settings.get('internal_only'):
            from flask_login import current_user
            if not current_user or not current_user.is_authenticated:
                return ServiceResult(success=False, error='This form is not available for public submission', status_code=403)

        # Check submission limit
        submission_limit = settings.get('submission_limit')
        if submission_limit:
            current_count = self.form_repo.count_submissions(form['id'])
            if current_count >= int(submission_limit):
                msg = settings.get('limit_message', 'This form is no longer accepting submissions.')
                return ServiceResult(success=False, error=msg, status_code=403)

        # Extract context fields before stripping (injected by frontend for voucher forms)
        explicit_approver_id = answers.pop('f_approver', None) or None
        if explicit_approver_id:
            try:
                explicit_approver_id = int(explicit_approver_id)
            except (ValueError, TypeError):
                explicit_approver_id = None
        context_company = answers.pop('f_company', None)
        context_department = answers.pop('f_department', None)
        start_date = answers.pop('f_start_date', None)

        # Strip unknown answer keys — only accept keys matching schema field IDs
        known_field_ids = {f.get('id') for f in schema if f.get('id')}
        answers = {k: v for k, v in answers.items() if k in known_field_ids}

        # Re-add context fields so they appear in stored answers (for approval title etc.)
        if context_company:
            answers['f_company'] = context_company
        if context_department:
            answers['f_department'] = context_department
        if start_date:
            answers['f_start_date'] = start_date

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
            source='web_internal' if user_id else 'web_public',
            company_id=form.get('company_id'),
            respondent_name=sanitized_respondent['name'] or None,
            respondent_email=sanitized_respondent['email'] or None,
            respondent_phone=sanitized_respondent['phone'] or None,
            respondent_ip=ip,
            respondent_user_id=user_id,
            utm_data=filtered_utm,
        )

        # Post-submission hooks (e.g. voucher creation)
        hook_data = self._run_post_submit_hooks(form, submission_id, answers, user_id)

        # Trigger approval if required
        if form.get('requires_approval'):
            respondent_with_user = {
                **sanitized_respondent,
                'user_id': user_id,
                'explicit_approver_id': explicit_approver_id,
            }
            self._trigger_approval(form, submission_id, respondent_with_user)
        else:
            # Even without approval, send submit notifications
            self._send_submit_notifications(form, submission_id, sanitized_respondent)

        thank_you = settings.get('thank_you_message', 'Thank you for your submission!')
        redirect_url = settings.get('redirect_url')

        response_data = {
            'submission_id': submission_id,
            'thank_you_message': thank_you,
            'redirect_url': redirect_url,
        }
        if hook_data:
            response_data['hook_data'] = hook_data
        return ServiceResult(success=True, data=response_data, status_code=201)

    def submit_internal(self, form_id: int, answers: Dict,
                        user: UserContext, source: str = 'web_internal') -> ServiceResult:
        """Handle an internal (authenticated) form submission."""
        form = self.form_repo.get_by_id(form_id)
        if not form:
            return ServiceResult(success=False, error='Form not found', status_code=404)

        schema = form.get('published_schema') or form.get('schema', [])

        # Extract context fields before stripping unknown keys
        explicit_approver_id = answers.get('f_approver') or None
        if explicit_approver_id:
            try:
                explicit_approver_id = int(explicit_approver_id)
            except (ValueError, TypeError):
                explicit_approver_id = None
        start_date = answers.get('f_start_date')

        # Strip unknown answer keys
        known_field_ids = {f.get('id') for f in schema if f.get('id')}
        answers = {k: v for k, v in answers.items() if k in known_field_ids}
        if start_date:
            answers['f_start_date'] = start_date

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

        # Post-submission hooks (e.g. voucher creation)
        hook_data = self._run_post_submit_hooks(form, submission_id, answers, user.user_id)

        if form.get('requires_approval'):
            self._trigger_approval(form, submission_id, {
                'user_id': user.user_id,
                'explicit_approver_id': explicit_approver_id,
            })

        response_data = {'submission_id': submission_id}
        if hook_data:
            response_data['hook_data'] = hook_data
        return ServiceResult(success=True, data=response_data, status_code=201)

    LEAVE_FORM_SLUG = 'bilet-de-invoire'
    LEAVE_REQUIRED_FIELDS = ('f_bi_leave_date', 'f_bi_start_time', 'f_bi_duration_hours', 'f_bi_reason')
    # Old contract, still sent by the live jarvis-mobile-2/-3 apps — no duration,
    # no consent, no signature. Keep accepting it until those apps are retired.
    LEAVE_REQUIRED_FIELDS_LEGACY = ('f_bi_leave_date', 'f_bi_start_time', 'f_bi_end_time', 'f_bi_reason')
    LEAVE_TERMS_TEXT = ('Declar că îmi asum responsabilitatea pentru orice eventual '
                        'eveniment neplăcut care ar putea surveni în legătură cu mine, '
                        'în această perioadă în care sunt învoit / învoită 🔒')

    @staticmethod
    def _is_new_leave_contract(answers) -> bool:
        """True when the submission uses the NEW (duration-based) web contract."""
        a = answers or {}
        return bool(str(a.get('f_bi_duration_hours', '')).strip())

    @staticmethod
    def _leave_permit_missing_fields(answers):
        """Required fields absent/blank from a code-defined Invoire submission (NEW contract)."""
        a = answers or {}
        return [k for k in FormService.LEAVE_REQUIRED_FIELDS if not str(a.get(k, '')).strip()]

    @staticmethod
    def _leave_permit_missing_fields_legacy(answers):
        """Required fields absent/blank for the OLD (mobile) Invoire contract."""
        a = answers or {}
        return [k for k in FormService.LEAVE_REQUIRED_FIELDS_LEGACY if not str(a.get(k, '')).strip()]

    @staticmethod
    def _leave_permit_precheck(answers):
        """Consent + signature presence. Returns error message or None."""
        a = answers or {}
        if not a.get('f_bi_terms_accepted'):
            return 'Trebuie să acceptați declarația de responsabilitate.'
        if not str(a.get('signature_image', '')).strip():
            return 'Semnătura este obligatorie.'
        return None

    def submit_leave_permit(self, answers: Dict, user: UserContext, ip_address=None) -> ServiceResult:
        """Create a Bilet de Invoire (code-defined Invoire module form).

        Branches on the presence of `f_bi_duration_hours`:
          - NEW (web) contract: server computes/validates hours from start +
            duration against the employee's Sincron window, requires consent
            + signature, and stores a frozen signature copy.
          - LEGACY (mobile) contract: no duration/consent/signature sent by
            the live jarvis-mobile-2/-3 apps — validate only the old required
            fields, skip alignment/cap/window checks, but still derive a
            numeric f_bi_hours from start/end so HR/pontaj/Time-Bank reporting
            works for mobile submissions too.
        """
        from core.connectors.connecteam.services.leave_schedule import (
            get_leave_schedule, validate_leave, compute_return, parse_hm)
        from datetime import datetime, timezone

        form = self.form_repo.get_by_slug(self.LEAVE_FORM_SLUG)
        if not form:
            return ServiceResult(success=False, error='Leave form not configured', status_code=404)

        answers = dict(answers or {})
        # Pull signature out so it never lands in the JSONB.
        signature_image = str(answers.pop('signature_image', '') or '').strip()

        if self._is_new_leave_contract(answers):
            missing = self._leave_permit_missing_fields(answers)
            if missing:
                return ServiceResult(success=False,
                    error=f'Missing required fields: {", ".join(missing)}', status_code=400)
            precheck = self._leave_permit_precheck({**answers, 'signature_image': signature_image})
            if precheck:
                return ServiceResult(success=False, error=precheck, status_code=400)
            if answers.get('f_bi_reason') not in ('Personal', 'Medical', 'Familial', 'Oficial', 'Altul'):
                return ServiceResult(success=False, error='Motiv invalid', status_code=400)

            schedule = get_leave_schedule(user.user_id, answers.get('f_bi_leave_date'))
            time_err = validate_leave(answers.get('f_bi_start_time'),
                                      answers.get('f_bi_duration_hours'), schedule)
            if time_err:
                return ServiceResult(success=False, error=time_err, status_code=400)

            duration = float(answers['f_bi_duration_hours'])
            answers['f_bi_hours'] = duration
            answers['f_bi_end_time'] = compute_return(answers['f_bi_start_time'], duration)
            answers['f_bi_terms_accepted'] = True
            answers['f_bi_terms_text'] = self.LEAVE_TERMS_TEXT
            answers['f_bi_terms_accepted_at'] = datetime.now(timezone.utc).isoformat()
        else:
            missing = self._leave_permit_missing_fields_legacy(answers)
            if missing:
                return ServiceResult(success=False,
                    error=f'Missing required fields: {", ".join(missing)}', status_code=400)

            # Derive numeric hours from start/end so pontaj/HR/Time-Bank still
            # get a usable value from legacy mobile submissions.
            s = parse_hm(answers.get('f_bi_start_time'))
            e = parse_hm(answers.get('f_bi_end_time'))
            if s is not None and e is not None and e > s:
                answers['f_bi_hours'] = round((e - s) / 60, 2)
            # f_bi_end_time stays exactly as sent by the client.

        answers = _sanitize_answers(answers)
        submission_id = self.submission_repo.create(
            form_id=form['id'], form_version=form.get('version', 1),
            answers=answers, form_schema_snapshot=[], source='web_internal',
            company_id=form.get('company_id'), respondent_user_id=user.user_id,
        )

        # Frozen per-submission signature copy → document_signatures.
        # Legacy mobile bodies send no signature — skip creating a row for them.
        if signature_image:
            try:
                from core.signatures.repositories.signature_repo import SignatureRepository
                SignatureRepository().create_signed('leave_permit', submission_id,
                                                     user.user_id, signature_image, ip_address)
            except Exception as e:
                logger.warning('signature persist failed for leave permit %s: %s', submission_id, e)

        if form.get('requires_approval'):
            self._trigger_approval(form, submission_id, {
                'user_id': user.user_id,
                'explicit_approver_id': answers.get('f_bi_approver') or None,
            })
            # _trigger_approval's own linking is unreliable (engine.submit returns
            # the full request row, not {'request_id': ...}), so link the request
            # to the submission explicitly — the Hub resolves the real approver
            # from the decision record via this id.
            try:
                from core.approvals.repositories import RequestRepository
                req_id = RequestRepository().get_pending_for_entity('form_submission', submission_id)
                if req_id:
                    self.submission_repo.set_approval_request(submission_id, req_id)
            except Exception as e:
                logger.warning('Could not link approval request for leave permit %s: %s', submission_id, e)

        return ServiceResult(success=True, data={'submission_id': submission_id}, status_code=201)

    # ============== Post-Submit Hooks ==============

    def _run_post_submit_hooks(self, form: dict, submission_id: int, answers: Dict, user_id: Optional[int]) -> Optional[Dict]:
        """Run form-specific hooks after submission. Returns optional hook_data for response."""
        slug = form.get('slug', '')
        try:
            if slug == 'voucher-issuance' and user_id:
                self._create_voucher_from_submission(form, submission_id, answers, user_id)
            # NOTE: 'test-drive' is intentionally NOT handled here. Test drives are
            # recorded exclusively via the in-module custom form
            # (POST /api/foi-parcurs/test-drive). See foi_parcurs/routes/test_drive.py.
        except Exception as e:
            logger.error('Post-submit hook failed for %s submission %s: %s', slug, submission_id, e)
        return None

    def _create_voucher_from_submission(self, form: dict, submission_id: int, answers: Dict, user_id: int):
        """Create a voucher record from a voucher-issuance form submission."""
        from accounting.vouchers.services.voucher_service import VoucherService

        # Map form field IDs to voucher data
        validity_str = answers.get('f_validity_months', '6 months')
        try:
            validity_months = int(str(validity_str).split()[0])
        except (ValueError, IndexError):
            validity_months = 6

        type_map = {
            'Value (LEI)': 'value',
            'Accessory Discount Code': 'accessory_discount_code',
            'Accessory Percentage': 'accessory_percentage',
            'Service Items': 'service_items',
        }
        raw_type = answers.get('f_voucher_type', 'Value (LEI)')
        voucher_type = type_map.get(raw_type, 'value')

        service_items = answers.get('f_service_items')
        if isinstance(service_items, str):
            import json as _json
            try:
                service_items = _json.loads(service_items)
            except (ValueError, TypeError):
                service_items = None

        # Get user's company_id
        from database import get_db, get_cursor, release_db
        conn = get_db()
        cur = get_cursor(conn)
        try:
            cur.execute('SELECT company_id FROM users WHERE id = %s', (user_id,))
            row = cur.fetchone()
            company_id = row['company_id'] if row else form.get('company_id')
        finally:
            release_db(conn)

        data = {
            'client_name': answers.get('f_client_name', ''),
            'contract_number': answers.get('f_contract_number', ''),
            'car_vin': answers.get('f_car_vin', ''),
            'validity_months': validity_months,
            'voucher_type': voucher_type,
            'value_lei': answers.get('f_value_lei'),
            'discount_code': answers.get('f_discount_code'),
            'discount_percentage': answers.get('f_discount_percentage'),
            'service_items': service_items if isinstance(service_items, list) else None,
            'notes': answers.get('f_notes'),
        }

        svc = VoucherService()
        voucher = svc.create_voucher(data=data, user_id=user_id, company_id=company_id)

        # Link submission to voucher
        conn = get_db()
        cur = get_cursor(conn)
        try:
            cur.execute('UPDATE vouchers SET form_submission_id = %s WHERE id = %s', (submission_id, voucher['id']))
            conn.commit()
        finally:
            release_db(conn)

        logger.info('Voucher %s created from form submission %s by user %s', voucher['id'], submission_id, user_id)

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

    def _resolve_form_approver(self, user_id, company_id, explicit_approver_id=None):
        """Resolve the approver for a form submission using VoucherService logic."""
        try:
            from accounting.vouchers.services import VoucherService
            approver = VoucherService().resolve_approver(
                user_id, company_id or 0,
                explicit_approver_id=explicit_approver_id,
            )
            return approver['id'] if approver else None
        except Exception as e:
            logger.warning(f'Failed to resolve approver for user {user_id}: {e}')
            return None

    @staticmethod
    def _build_stakeholder_ids(primary_id, answers):
        """Deduped [primary, second?] approver ids for either-approves routing."""
        def _as_int(v):
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        candidates = [primary_id, _as_int((answers or {}).get('f_bi_second_approver'))]
        out, seen = [], set()
        for a in candidates:
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        return out

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

            # Resolve approver from org hierarchy
            requested_by = respondent_info.get('user_id', form.get('owner_id'))
            approver_user_id = self._resolve_form_approver(
                requested_by, form.get('company_id'),
                respondent_info.get('explicit_approver_id'),
            )

            # Build human-readable title: "Voucher — Dept — Client Name"
            sub = self.submission_repo.get_by_id(submission_id)
            answers = (sub.get('answers') or {}) if sub else {}
            title_parts = [form.get('name', 'Form Submission')]
            if answers.get('f_department'):
                title_parts.append(str(answers['f_department']))
            if answers.get('f_client_name'):
                title_parts.append(str(answers['f_client_name']))
            title = ' — '.join(title_parts)

            # Primary (org hierarchy) + optional second approver — either may approve.
            stakeholder_ids = self._build_stakeholder_ids(approver_user_id, answers)

            context = {
                'title': title,
                'form_id': form['id'],
                'form_name': form.get('name', ''),
                'submission_id': submission_id,
                'respondent_email': respondent_info.get('email', ''),
                'respondent_name': respondent_info.get('name', ''),
                'company_id': form.get('company_id'),
                'approver_user_id': approver_user_id,
                'stakeholder_approver_ids': stakeholder_ids,
                'notify_on_submit': approval_config.get('notify_on_submit', []),
                'notify_on_approve': approval_config.get('notify_on_approve', []),
                'notify_on_reject': approval_config.get('notify_on_reject', []),
                'notify_respondent': approval_config.get('notify_respondent', False),
                'requires_signature': approval_config.get('requires_signature', False),
            }
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
