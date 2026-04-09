"""Connecteam service — webhook processing, user mapping, config management.

Unlike Sincron/BioStar, this connector is push-based (webhook-driven).
No scheduled sync — data arrives via Connecteam webhook POST.
"""

import json
import hmac
import hashlib
import logging
from datetime import datetime

from ..client.connecteam_client import ConnecteamClient
from ..client.exceptions import ConnecteamError
from ..repositories.connecteam_repository import ConnecteamRepository
from ..config import (BILET_INVOIRE_FORM_ID, BILET_INVOIRE_FORM_NAME,
                       SUPPORTED_EVENT_TYPES, JARVIS_LEAVE_FORM_SLUG)
from core.connectors.repositories.connector_repository import ConnectorRepository

logger = logging.getLogger('jarvis.connecteam.service')


def _safe_float(val):
    """Convert value to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


class ConnecteamService:
    """Business logic for Connecteam webhook connector."""

    def __init__(self):
        self.repo = ConnecteamRepository()
        self.connector_repo = ConnectorRepository()

    # ── Connection config ──

    def get_connection_config(self):
        """Get stored Connecteam connector configuration."""
        connector = self.connector_repo.get_by_type('connecteam')
        if not connector:
            return None
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        credentials = connector.get('credentials') or {}
        if isinstance(credentials, str):
            credentials = json.loads(credentials)
        return {
            'id': connector['id'],
            'status': connector.get('status', 'disconnected'),
            'last_sync': str(connector['last_sync']) if connector.get('last_sync') else None,
            'form_id': config.get('form_id', BILET_INVOIRE_FORM_ID),
            'form_name': config.get('form_name', BILET_INVOIRE_FORM_NAME),
            'webhook_url': config.get('webhook_url'),
            'webhook_id': config.get('webhook_id'),
            'has_client_id': bool(credentials.get('client_id')),
            'has_client_secret': bool(credentials.get('client_secret')),
            'has_webhook_secret': bool(credentials.get('webhook_secret')),
            'field_mapping': config.get('field_mapping', {}),
        }

    def save_connection(self, client_id, client_secret, webhook_secret=None):
        """Save or update Connecteam connector config."""
        if not client_id or not client_secret:
            raise ValueError('client_id and client_secret are required')

        credentials = {
            'client_id': client_id,
            'client_secret': client_secret,
        }
        if webhook_secret:
            credentials['webhook_secret'] = webhook_secret

        config = {
            'form_id': BILET_INVOIRE_FORM_ID,
            'form_name': BILET_INVOIRE_FORM_NAME,
        }

        connector = self.connector_repo.get_by_type('connecteam')
        if connector:
            # Preserve existing config fields (webhook_url, webhook_id, field_mapping)
            existing_config = connector.get('config') or {}
            if isinstance(existing_config, str):
                existing_config = json.loads(existing_config)
            existing_config.update(config)
            # Preserve existing webhook_secret if not provided
            existing_creds = connector.get('credentials') or {}
            if isinstance(existing_creds, str):
                existing_creds = json.loads(existing_creds)
            if not webhook_secret and existing_creds.get('webhook_secret'):
                credentials['webhook_secret'] = existing_creds['webhook_secret']

            self.connector_repo.update(
                connector['id'],
                config=existing_config,
                credentials=credentials,
                status='connected',
            )
            return connector['id']
        else:
            return self.connector_repo.save(
                connector_type='connecteam',
                name='Connecteam Forms',
                status='connected',
                config=config,
                credentials=credentials,
            )

    def _get_credentials(self):
        """Get client_id and client_secret from connector config."""
        connector = self.connector_repo.get_by_type('connecteam')
        if not connector:
            return None, None, None
        credentials = connector.get('credentials') or {}
        if isinstance(credentials, str):
            credentials = json.loads(credentials)
        return (
            credentials.get('client_id'),
            credentials.get('client_secret'),
            credentials.get('webhook_secret'),
        )

    def _get_config(self):
        """Get connector config dict."""
        connector = self.connector_repo.get_by_type('connecteam')
        if not connector:
            return {}
        config = connector.get('config') or {}
        if isinstance(config, str):
            config = json.loads(config)
        return config

    def _get_client(self):
        """Get an authenticated ConnecteamClient."""
        client_id, client_secret, _ = self._get_credentials()
        if not client_id or not client_secret:
            raise ConnecteamError('Connecteam credentials not configured')
        return ConnecteamClient(client_id, client_secret)

    # ── Test connection ──

    def test_connection(self):
        """Test OAuth connectivity."""
        client = self._get_client()
        try:
            return client.test_connection()
        finally:
            client.close()

    # ── Webhook registration ──

    def register_webhook(self, callback_url):
        """Register JARVIS webhook with Connecteam API."""
        client = self._get_client()
        _, _, webhook_secret = self._get_credentials()

        try:
            result = client.register_webhook(
                name='JARVIS Bilet de Invoire',
                url=callback_url,
                secret_key=webhook_secret,
                form_id=BILET_INVOIRE_FORM_ID,
            )
        finally:
            client.close()

        # Store webhook_id and URL in config
        webhook_data = result.get('data', result)
        webhook_id = webhook_data.get('id')
        if webhook_id:
            config = self._get_config()
            config['webhook_url'] = callback_url
            config['webhook_id'] = webhook_id
            connector = self.connector_repo.get_by_type('connecteam')
            if connector:
                self.connector_repo.update(connector['id'], config=config)

        return result

    def list_webhooks(self):
        """List registered webhooks."""
        client = self._get_client()
        try:
            return client.list_webhooks()
        finally:
            client.close()

    def delete_webhook(self, webhook_id):
        """Delete a registered webhook."""
        client = self._get_client()
        try:
            return client.delete_webhook(webhook_id)
        finally:
            client.close()

    # ── Webhook processing ──

    def verify_webhook(self, raw_body, signature_header):
        """Verify webhook HMAC signature.

        Returns True if signature is valid or no secret is configured (dev mode).
        """
        _, _, webhook_secret = self._get_credentials()
        if not webhook_secret:
            logger.warning('No webhook_secret configured — skipping verification')
            return True
        if not signature_header:
            return False

        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header)

    def process_webhook(self, payload):
        """Process an incoming webhook payload.

        Returns dict with processing result.
        """
        request_id = payload.get('requestId', '')
        event_type = payload.get('eventType', '')
        data = payload.get('data', {})
        form_id = data.get('formId')

        # Log webhook
        log = self.repo.log_webhook(
            request_id=request_id,
            event_type=event_type,
            form_id=form_id,
            raw_payload=payload,
        )
        log_id = log['id'] if log else None

        try:
            # Check event type
            if event_type not in SUPPORTED_EVENT_TYPES:
                if log_id:
                    self.repo.update_webhook_log(log_id, 'ignored',
                                                 f'Unsupported event type: {event_type}')
                return {'status': 'ignored', 'reason': f'Unsupported event type: {event_type}'}

            # Check form ID
            target_form_id = self._get_config().get('form_id', BILET_INVOIRE_FORM_ID)
            if form_id and form_id != target_form_id:
                if log_id:
                    self.repo.update_webhook_log(log_id, 'ignored',
                                                 f'Wrong form ID: {form_id}')
                return {'status': 'ignored', 'reason': f'Wrong form ID: {form_id}'}

            # Process form submission
            result = self._process_form_submission(data, payload, event_type)

            if log_id:
                self.repo.update_webhook_log(log_id, 'processed')

            # Update connector last_sync
            connector = self.connector_repo.get_by_type('connecteam')
            if connector:
                self.connector_repo.update(connector['id'], last_sync=datetime.now())

            return {'status': 'processed', **result}

        except Exception as exc:
            logger.exception('Error processing webhook %s: %s', request_id, exc)
            if log_id:
                self.repo.update_webhook_log(log_id, 'failed', str(exc))
            return {'status': 'failed', 'error': str(exc)}

    def _process_form_submission(self, data, full_payload, event_type):
        """Process a form_submission or form_submission_edited event."""
        submission_id = data.get('formSubmissionId', '')
        form_id = data.get('formId')
        connecteam_user_id = data.get('submittingUserId')
        submission_ts = data.get('submissionTimestamp')
        submission_tz = data.get('submissionTimezone', 'Europe/Bucharest')
        entry_num = data.get('entryNum')
        is_anonymous = data.get('isAnonymous', False)
        answers = data.get('answers', [])

        # Convert Unix timestamp to datetime
        submission_dt = None
        if submission_ts:
            submission_dt = datetime.utcfromtimestamp(submission_ts)

        # Upsert Connecteam user (organic discovery)
        if connecteam_user_id:
            user_row = self.repo.upsert_user(connecteam_user_id)
            mapped_jarvis_id = user_row.get('mapped_jarvis_user_id') if user_row else None
        else:
            mapped_jarvis_id = None

        # Parse form fields
        parsed = self._parse_bilet_invoire(answers)

        # Upsert submission
        sub_row = self.repo.upsert_submission(
            submission_id=str(submission_id),
            form_id=form_id,
            form_name=BILET_INVOIRE_FORM_NAME,
            connecteam_user_id=connecteam_user_id,
            mapped_jarvis_user_id=mapped_jarvis_id,
            submission_timestamp=submission_dt,
            submission_timezone=submission_tz,
            entry_num=entry_num,
            is_anonymous=is_anonymous,
            leave_date=parsed.get('leave_date'),
            leave_start_time=parsed.get('leave_start_time'),
            leave_end_time=parsed.get('leave_end_time'),
            leave_hours=parsed.get('leave_hours'),
            leave_reason=parsed.get('leave_reason'),
            leave_destination=parsed.get('leave_destination'),
            approved_by=parsed.get('approved_by'),
            raw_answers=answers,
            raw_payload=full_payload,
            event_type=event_type,
        )

        logger.info('Processed submission %s for CT user %s (JARVIS user %s)',
                     submission_id, connecteam_user_id, mapped_jarvis_id)

        return {
            'submission_id': str(submission_id),
            'connecteam_user_id': connecteam_user_id,
            'mapped_jarvis_user_id': mapped_jarvis_id,
            'parsed_fields': list(parsed.keys()),
        }

    def _parse_bilet_invoire(self, answers):
        """Parse "Bilet de invoire" form answers into structured fields.

        Attempts to extract: leave_date, leave_start_time, leave_end_time,
        leave_hours, leave_reason, leave_destination, approved_by.

        Uses field_mapping from config if available, otherwise uses heuristics
        based on question type and position.
        """
        config = self._get_config()
        field_mapping = config.get('field_mapping', {})
        result = {}

        if not answers:
            return result

        # If we have a field_mapping, use it (questionId → field name)
        if field_mapping:
            for answer in answers:
                if answer.get('wasSubmittedEmpty'):
                    continue
                qid = answer.get('questionId', '')
                for field_name, mapped_qid in field_mapping.items():
                    if qid == mapped_qid:
                        result[field_name] = self._extract_answer_value(answer)
            return result

        # Heuristic parsing: iterate answers and guess by type/position
        datetime_fields = []
        text_fields = []

        for answer in answers:
            if answer.get('wasSubmittedEmpty') or answer.get('wasHidden'):
                continue

            q_type = answer.get('questionType', '')
            value = self._extract_answer_value(answer)

            if value is None:
                continue

            if q_type in ('datetime', 'date', 'time'):
                datetime_fields.append(value)
            elif q_type in ('openEnded', 'text', 'paragraph'):
                text_fields.append(str(value))
            elif q_type in ('multipleChoice', 'dropdown'):
                text_fields.append(str(value))
            elif q_type == 'numeric':
                # Likely hours
                try:
                    result['leave_hours'] = float(value)
                except (ValueError, TypeError):
                    text_fields.append(str(value))

        # Assign datetime fields (first = date, second = start, third = end)
        if len(datetime_fields) >= 1:
            result['leave_date'] = datetime_fields[0]
        if len(datetime_fields) >= 2:
            result['leave_start_time'] = datetime_fields[1]
        if len(datetime_fields) >= 3:
            result['leave_end_time'] = datetime_fields[2]

        # Assign text fields (first = reason, second = destination)
        if len(text_fields) >= 1:
            result['leave_reason'] = text_fields[0]
        if len(text_fields) >= 2:
            result['leave_destination'] = text_fields[1]
        if len(text_fields) >= 3:
            result['approved_by'] = text_fields[2]

        return result

    @staticmethod
    def _extract_answer_value(answer):
        """Extract the actual value from a Connecteam answer object."""
        # Direct value field
        if 'value' in answer and answer['value'] is not None:
            return answer['value']
        # Multiple choice — join selected answers
        selected = answer.get('selectedAnswers', [])
        if selected:
            labels = [s.get('label', s.get('value', str(s)))
                      for s in selected if isinstance(s, dict)]
            return ', '.join(labels) if labels else str(selected)
        # Images/signatures
        images = answer.get('images', [])
        if images:
            return images[0].get('url', '') if isinstance(images[0], dict) else str(images[0])
        return None

    # ── User mapping ──

    def auto_map_users(self):
        """Auto-map Connecteam users to JARVIS users (email → phone → name)."""
        email_mapped = self.repo.auto_map_by_email() or 0
        phone_mapped = self.repo.auto_map_by_phone() or 0
        name_mapped = self.repo.auto_map_by_name() or 0

        # Update submissions mapping for newly mapped users
        mapped_users = self.repo.get_all_users()
        for user in mapped_users:
            if user.get('mapped_jarvis_user_id'):
                self.repo.update_submissions_mapping(
                    user['connecteam_user_id'],
                    user['mapped_jarvis_user_id'],
                )

        return {
            'success': True,
            'email_mapped': email_mapped,
            'phone_mapped': phone_mapped,
            'name_mapped': name_mapped,
            'total_mapped': email_mapped + phone_mapped + name_mapped,
        }

    def update_user_mapping(self, connecteam_user_id, jarvis_user_id):
        """Manually map a Connecteam user to a JARVIS user."""
        self.repo.update_user_mapping(connecteam_user_id, jarvis_user_id, method='manual')
        # Also update existing submissions
        self.repo.update_submissions_mapping(connecteam_user_id, jarvis_user_id)

    def remove_user_mapping(self, connecteam_user_id):
        """Remove mapping for a Connecteam user."""
        self.repo.remove_user_mapping(connecteam_user_id)

    # ── Query ──

    def get_user_submissions(self, jarvis_user_id, year=None, month=None):
        """Get leave permission submissions for a JARVIS user.

        Combines data from two sources:
        - Connecteam webhook submissions (connecteam_form_submissions)
        - JARVIS internal form submissions (form_submissions for 'bilet-de-invoire')
        """
        # Connecteam submissions
        ct_submissions = self.repo.get_submissions_by_jarvis_user(
            jarvis_user_id, year, month
        )
        # Tag source
        for s in ct_submissions:
            s['source'] = 'connecteam'

        # JARVIS form submissions
        jarvis_submissions = self._get_jarvis_form_submissions(
            jarvis_user_id, year, month
        )

        # Merge and sort by leave_date descending
        all_subs = ct_submissions + jarvis_submissions
        all_subs.sort(
            key=lambda s: s.get('leave_date') or s.get('created_at') or '',
            reverse=True,
        )
        return all_subs

    def _get_jarvis_form_submissions(self, jarvis_user_id, year=None, month=None):
        """Fetch JARVIS internal 'Bilet de Invoire' form submissions for a user."""
        from database import get_db, get_cursor, release_db, dict_from_row

        conn = get_db()
        cursor = get_cursor(conn)
        try:
            # Find the JARVIS leave form by slug
            cursor.execute(
                "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL LIMIT 1",
                (JARVIS_LEAVE_FORM_SLUG,)
            )
            form_row = cursor.fetchone()
            if not form_row:
                return []

            form_id = form_row['id'] if isinstance(form_row, dict) else form_row[0]

            query = '''
                SELECT fs.id, fs.form_id, f.name AS form_name,
                       fs.answers, fs.status, fs.source,
                       fs.respondent_user_id, fs.created_at::text,
                       u.name AS respondent_name
                FROM form_submissions fs
                JOIN forms f ON f.id = fs.form_id
                LEFT JOIN users u ON u.id = fs.respondent_user_id
                WHERE fs.form_id = %s AND fs.respondent_user_id = %s
            '''
            params = [form_id, jarvis_user_id]

            if year:
                query += " AND EXTRACT(YEAR FROM fs.created_at) = %s"
                params.append(year)
            if month:
                query += " AND EXTRACT(MONTH FROM fs.created_at) = %s"
                params.append(month)

            query += ' ORDER BY fs.created_at DESC'
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                r = dict_from_row(row) if not isinstance(row, dict) else dict(row)
                answers = r.get('answers', {})
                if isinstance(answers, str):
                    answers = json.loads(answers)

                # Map JARVIS form answers to the same shape as Connecteam submissions
                results.append({
                    'id': r['id'],
                    'submission_id': f"jarvis-{r['id']}",
                    'form_id': r['form_id'],
                    'form_name': r.get('form_name', BILET_INVOIRE_FORM_NAME),
                    'connecteam_user_id': None,
                    'mapped_jarvis_user_id': jarvis_user_id,
                    'connecteam_user_name': r.get('respondent_name'),
                    'submission_timestamp': r.get('created_at'),
                    'leave_date': answers.get('f_bi_leave_date'),
                    'leave_start_time': answers.get('f_bi_start_time'),
                    'leave_end_time': answers.get('f_bi_end_time'),
                    'leave_hours': _safe_float(answers.get('f_bi_hours')),
                    'leave_reason': answers.get('f_bi_reason'),
                    'leave_destination': answers.get('f_bi_destination'),
                    'approved_by': None,
                    'status': r.get('status', 'new'),
                    'event_type': 'jarvis_form',
                    'entry_num': None,
                    'received_at': r.get('created_at'),
                    'created_at': r.get('created_at'),
                    'source': 'jarvis',
                })
            return results
        except Exception as e:
            logger.error('Error fetching JARVIS form submissions: %s', e)
            return []
        finally:
            release_db(conn)

    def get_status(self):
        """Get overall connector status."""
        config = self.get_connection_config()
        stats = self.repo.get_stats()
        return {
            'connected': config is not None and config.get('status') == 'connected',
            'status': config.get('status', 'disconnected') if config else 'disconnected',
            'last_sync': config.get('last_sync') if config else None,
            'form_name': config.get('form_name', BILET_INVOIRE_FORM_NAME) if config else BILET_INVOIRE_FORM_NAME,
            'webhook_registered': bool(config.get('webhook_id')) if config else False,
            'total_users': stats.get('total_users', 0) if stats else 0,
            'mapped_users': stats.get('mapped_users', 0) if stats else 0,
            'unmapped_users': stats.get('unmapped_users', 0) if stats else 0,
            'total_submissions': stats.get('total_submissions', 0) if stats else 0,
            'last_webhook_at': stats.get('last_webhook_at') if stats else None,
        }
