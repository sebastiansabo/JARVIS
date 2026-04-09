"""Connecteam connector data access — users, form submissions, webhook log."""

import json
from core.base_repository import BaseRepository


class ConnecteamRepository(BaseRepository):
    """CRUD for connecteam_users, connecteam_form_submissions, connecteam_webhook_log."""

    # ── User operations ──

    def upsert_user(self, connecteam_user_id, name=None, email=None, phone=None):
        """Insert or update a Connecteam user record."""
        return self.execute('''
            INSERT INTO connecteam_users
                (connecteam_user_id, connecteam_user_name, connecteam_email, connecteam_phone)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (connecteam_user_id) DO UPDATE SET
                connecteam_user_name = COALESCE(EXCLUDED.connecteam_user_name, connecteam_users.connecteam_user_name),
                connecteam_email = COALESCE(EXCLUDED.connecteam_email, connecteam_users.connecteam_email),
                connecteam_phone = COALESCE(EXCLUDED.connecteam_phone, connecteam_users.connecteam_phone),
                updated_at = NOW()
            RETURNING id, connecteam_user_id, mapped_jarvis_user_id
        ''', (connecteam_user_id, name, email, phone), returning=True)

    def get_user_by_connecteam_id(self, connecteam_user_id):
        """Get Connecteam user by their Connecteam ID."""
        return self.query_one('''
            SELECT cu.*, u.name AS mapped_jarvis_user_name
            FROM connecteam_users cu
            LEFT JOIN users u ON u.id = cu.mapped_jarvis_user_id
            WHERE cu.connecteam_user_id = %s
        ''', (connecteam_user_id,))

    def get_user_by_jarvis_id(self, jarvis_user_id):
        """Get Connecteam user mapped to a JARVIS user."""
        return self.query_one('''
            SELECT cu.*, u.name AS mapped_jarvis_user_name
            FROM connecteam_users cu
            LEFT JOIN users u ON u.id = cu.mapped_jarvis_user_id
            WHERE cu.mapped_jarvis_user_id = %s AND cu.is_active = TRUE
            LIMIT 1
        ''', (jarvis_user_id,))

    def get_all_users(self, active_only=True):
        """Get all Connecteam users with mapping info."""
        query = '''
            SELECT cu.id, cu.connecteam_user_id, cu.connecteam_user_name,
                   cu.connecteam_email, cu.connecteam_phone,
                   cu.mapped_jarvis_user_id, cu.mapping_method,
                   cu.mapping_confidence, cu.is_active,
                   cu.created_at, cu.updated_at,
                   u.name AS mapped_jarvis_user_name
            FROM connecteam_users cu
            LEFT JOIN users u ON u.id = cu.mapped_jarvis_user_id
            WHERE 1=1
        '''
        params = []
        if active_only:
            query += ' AND cu.is_active = TRUE'
        query += ' ORDER BY cu.connecteam_user_name'
        return self.query_all(query, tuple(params))

    def get_unmapped_users(self):
        """Get users not yet mapped to JARVIS users."""
        return self.query_all('''
            SELECT id, connecteam_user_id, connecteam_user_name,
                   connecteam_email, connecteam_phone,
                   is_active, created_at
            FROM connecteam_users
            WHERE mapped_jarvis_user_id IS NULL AND is_active = TRUE
            ORDER BY connecteam_user_name
        ''')

    def update_user_mapping(self, connecteam_user_id, jarvis_user_id, method='manual'):
        """Manually map a Connecteam user to a JARVIS user."""
        return self.execute('''
            UPDATE connecteam_users
            SET mapped_jarvis_user_id = %s,
                mapping_method = %s,
                mapping_confidence = 100,
                updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (jarvis_user_id, method, connecteam_user_id))

    def remove_user_mapping(self, connecteam_user_id):
        """Remove mapping for a Connecteam user."""
        return self.execute('''
            UPDATE connecteam_users
            SET mapped_jarvis_user_id = NULL,
                mapping_method = NULL,
                mapping_confidence = 0,
                updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (connecteam_user_id,))

    def auto_map_by_email(self):
        """Auto-map Connecteam users to JARVIS users by email match."""
        return self.execute('''
            UPDATE connecteam_users cu
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'email',
                mapping_confidence = 100,
                updated_at = NOW()
            FROM users u
            WHERE LOWER(cu.connecteam_email) = LOWER(u.email)
              AND cu.mapped_jarvis_user_id IS NULL
              AND cu.connecteam_email IS NOT NULL
              AND u.is_active = TRUE
        ''')

    def auto_map_by_phone(self):
        """Auto-map Connecteam users to JARVIS users by phone match."""
        return self.execute('''
            UPDATE connecteam_users cu
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'phone',
                mapping_confidence = 95,
                updated_at = NOW()
            FROM users u
            WHERE REPLACE(REPLACE(cu.connecteam_phone, ' ', ''), '+', '')
                = REPLACE(REPLACE(u.phone, ' ', ''), '+', '')
              AND cu.mapped_jarvis_user_id IS NULL
              AND cu.connecteam_phone IS NOT NULL
              AND u.phone IS NOT NULL
              AND u.is_active = TRUE
        ''')

    def auto_map_by_name(self):
        """Auto-map Connecteam users to JARVIS users by name match."""
        return self.execute('''
            UPDATE connecteam_users cu
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'name',
                mapping_confidence = 80,
                updated_at = NOW()
            FROM users u
            WHERE LOWER(TRIM(cu.connecteam_user_name)) = LOWER(TRIM(u.name))
              AND cu.mapped_jarvis_user_id IS NULL
              AND cu.connecteam_user_name IS NOT NULL
              AND u.is_active = TRUE
        ''')

    # ── Submission operations ──

    def upsert_submission(self, submission_id, form_id, connecteam_user_id,
                          submission_timestamp, form_name=None,
                          mapped_jarvis_user_id=None, submission_timezone=None,
                          entry_num=None, is_anonymous=False,
                          leave_date=None, leave_start_time=None,
                          leave_end_time=None, leave_hours=None,
                          leave_reason=None, leave_destination=None,
                          approved_by=None, status='submitted',
                          raw_answers=None, raw_payload=None,
                          event_type='form_submission'):
        """Insert or update a form submission."""
        return self.execute('''
            INSERT INTO connecteam_form_submissions
                (submission_id, form_id, form_name, connecteam_user_id,
                 mapped_jarvis_user_id, submission_timestamp, submission_timezone,
                 entry_num, is_anonymous,
                 leave_date, leave_start_time, leave_end_time, leave_hours,
                 leave_reason, leave_destination, approved_by, status,
                 raw_answers, raw_payload, event_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (submission_id) DO UPDATE SET
                form_name = COALESCE(EXCLUDED.form_name, connecteam_form_submissions.form_name),
                mapped_jarvis_user_id = COALESCE(EXCLUDED.mapped_jarvis_user_id, connecteam_form_submissions.mapped_jarvis_user_id),
                leave_date = COALESCE(EXCLUDED.leave_date, connecteam_form_submissions.leave_date),
                leave_start_time = COALESCE(EXCLUDED.leave_start_time, connecteam_form_submissions.leave_start_time),
                leave_end_time = COALESCE(EXCLUDED.leave_end_time, connecteam_form_submissions.leave_end_time),
                leave_hours = COALESCE(EXCLUDED.leave_hours, connecteam_form_submissions.leave_hours),
                leave_reason = COALESCE(EXCLUDED.leave_reason, connecteam_form_submissions.leave_reason),
                leave_destination = COALESCE(EXCLUDED.leave_destination, connecteam_form_submissions.leave_destination),
                approved_by = COALESCE(EXCLUDED.approved_by, connecteam_form_submissions.approved_by),
                status = EXCLUDED.status,
                raw_answers = EXCLUDED.raw_answers,
                raw_payload = EXCLUDED.raw_payload,
                event_type = EXCLUDED.event_type,
                updated_at = NOW()
            RETURNING id, submission_id, mapped_jarvis_user_id
        ''', (submission_id, form_id, form_name, connecteam_user_id,
              mapped_jarvis_user_id, submission_timestamp, submission_timezone,
              entry_num, is_anonymous,
              leave_date, leave_start_time, leave_end_time, leave_hours,
              leave_reason, leave_destination, approved_by, status,
              json.dumps(raw_answers or []), json.dumps(raw_payload) if raw_payload else None,
              event_type), returning=True)

    def get_submissions_by_jarvis_user(self, jarvis_user_id, year=None, month=None):
        """Get leave permission submissions for a JARVIS user."""
        query = '''
            SELECT cfs.id, cfs.submission_id, cfs.form_id, cfs.form_name,
                   cfs.connecteam_user_id, cfs.mapped_jarvis_user_id,
                   cfs.submission_timestamp::text,
                   cfs.leave_date::text, cfs.leave_start_time::text,
                   cfs.leave_end_time::text, cfs.leave_hours,
                   cfs.leave_reason, cfs.leave_destination, cfs.approved_by,
                   cfs.status, cfs.event_type, cfs.entry_num,
                   cfs.received_at::text, cfs.created_at::text,
                   cu.connecteam_user_name
            FROM connecteam_form_submissions cfs
            LEFT JOIN connecteam_users cu ON cu.connecteam_user_id = cfs.connecteam_user_id
            WHERE cfs.mapped_jarvis_user_id = %s
        '''
        params = [jarvis_user_id]
        if year:
            query += ' AND EXTRACT(YEAR FROM cfs.leave_date) = %s'
            params.append(year)
        if month:
            query += ' AND EXTRACT(MONTH FROM cfs.leave_date) = %s'
            params.append(month)
        query += ' ORDER BY cfs.leave_date DESC, cfs.submission_timestamp DESC'
        return self.query_all(query, tuple(params))

    def get_recent_submissions(self, limit=50):
        """Get most recent submissions across all users."""
        return self.query_all('''
            SELECT cfs.id, cfs.submission_id, cfs.form_name,
                   cfs.connecteam_user_id, cfs.mapped_jarvis_user_id,
                   cfs.submission_timestamp::text,
                   cfs.leave_date::text, cfs.leave_hours,
                   cfs.leave_reason, cfs.status, cfs.event_type,
                   cu.connecteam_user_name,
                   u.name AS jarvis_user_name
            FROM connecteam_form_submissions cfs
            LEFT JOIN connecteam_users cu ON cu.connecteam_user_id = cfs.connecteam_user_id
            LEFT JOIN users u ON u.id = cfs.mapped_jarvis_user_id
            ORDER BY cfs.received_at DESC
            LIMIT %s
        ''', (limit,))

    def update_submissions_mapping(self, connecteam_user_id, jarvis_user_id):
        """Update mapped_jarvis_user_id on all submissions for a Connecteam user."""
        return self.execute('''
            UPDATE connecteam_form_submissions
            SET mapped_jarvis_user_id = %s, updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (jarvis_user_id, connecteam_user_id))

    # ── Webhook log ──

    def log_webhook(self, request_id, event_type, form_id, raw_payload,
                    status='received'):
        """Log an incoming webhook event."""
        return self.execute('''
            INSERT INTO connecteam_webhook_log
                (request_id, event_type, form_id, status, raw_payload)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (request_id, event_type, form_id, status,
              json.dumps(raw_payload)), returning=True)

    def update_webhook_log(self, log_id, status, error_message=None):
        """Update webhook log entry status."""
        return self.execute('''
            UPDATE connecteam_webhook_log
            SET status = %s, error_message = %s
            WHERE id = %s
        ''', (status, error_message, log_id))

    def get_webhook_log(self, limit=50):
        """Get recent webhook log entries."""
        return self.query_all('''
            SELECT id, request_id, event_type, form_id, status,
                   error_message, received_at::text
            FROM connecteam_webhook_log
            ORDER BY received_at DESC
            LIMIT %s
        ''', (limit,))

    # ── Stats ──

    def get_stats(self):
        """Get connector statistics."""
        return self.query_one('''
            SELECT
                (SELECT COUNT(*) FROM connecteam_users WHERE is_active = TRUE) AS total_users,
                (SELECT COUNT(*) FROM connecteam_users
                 WHERE mapped_jarvis_user_id IS NOT NULL AND is_active = TRUE) AS mapped_users,
                (SELECT COUNT(*) FROM connecteam_users
                 WHERE mapped_jarvis_user_id IS NULL AND is_active = TRUE) AS unmapped_users,
                (SELECT COUNT(*) FROM connecteam_form_submissions) AS total_submissions,
                (SELECT MAX(received_at)::text FROM connecteam_webhook_log
                 WHERE status = 'processed') AS last_webhook_at
        ''')
