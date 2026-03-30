"""Notification repository.

Handles all database operations for notification settings, logs, user notifications,
push notification categories, and rate limiting.
"""

import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.notifications.repository')


# ============== Push Notification Categories ==============

class PushCategoryRepository(BaseRepository):
    """CRUD for push_notification_categories table."""

    def get_all(self):
        return self.query_all(
            'SELECT * FROM push_notification_categories ORDER BY id'
        )

    def get_by_slug(self, slug):
        return self.query_one(
            'SELECT * FROM push_notification_categories WHERE slug = %s', (slug,)
        )

    def create(self, slug, name, description=None, priority='normal',
               max_per_hour=None, ttl_seconds=None, android_channel_id='default_notifications'):
        return self.execute(
            '''INSERT INTO push_notification_categories
               (slug, name, description, priority, max_per_hour, ttl_seconds, android_channel_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *''',
            (slug, name, description, priority, max_per_hour, ttl_seconds, android_channel_id),
            returning=True,
        )

    def update(self, category_id, **fields):
        if not fields:
            return None
        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [category_id]
        return self.execute(
            f'UPDATE push_notification_categories SET {sets}, updated_at = NOW() WHERE id = %s RETURNING *',
            tuple(vals), returning=True,
        )

    def delete(self, category_id):
        return self.execute(
            'DELETE FROM push_notification_categories WHERE id = %s AND is_builtin = FALSE',
            (category_id,),
        )

    def get_all_with_stats(self):
        """Get all categories with 24h usage counts."""
        return self.query_all('''
            SELECT c.*,
                   COALESCE(r.cnt, 0) AS sends_24h
            FROM push_notification_categories c
            LEFT JOIN (
                SELECT category_slug, COUNT(*) AS cnt
                FROM push_rate_limit_log
                WHERE sent_at > NOW() - INTERVAL '24 hours'
                GROUP BY category_slug
            ) r ON r.category_slug = c.slug
            ORDER BY c.id
        ''')


# ============== Push Rate Limit Log ==============

class PushRateLimitRepository(BaseRepository):
    """Rate limit tracking for push notifications."""

    def count_recent(self, user_id, category_slug, window_seconds=3600):
        """Count pushes sent to a user in a category within the time window."""
        row = self.query_one(
            '''SELECT COUNT(*) AS cnt FROM push_rate_limit_log
               WHERE user_id = %s AND category_slug = %s
                 AND sent_at > NOW() - INTERVAL '%s seconds' ''',
            (user_id, category_slug, window_seconds),
        )
        return row['cnt'] if row else 0

    def record(self, user_id, category_slug):
        """Record a push send for rate limiting."""
        self.execute(
            'INSERT INTO push_rate_limit_log (user_id, category_slug) VALUES (%s, %s)',
            (user_id, category_slug),
        )

    def record_bulk(self, user_ids, category_slug):
        """Record push sends for multiple users."""
        if not user_ids:
            return
        def _work(cursor):
            for uid in user_ids:
                cursor.execute(
                    'INSERT INTO push_rate_limit_log (user_id, category_slug) VALUES (%s, %s)',
                    (uid, category_slug),
                )
        self.execute_many(_work)

    def cleanup_old(self, days=7):
        """Delete rate limit log entries older than N days."""
        return self.execute(
            "DELETE FROM push_rate_limit_log WHERE sent_at < NOW() - INTERVAL '%s days'",
            (days,),
        )

    def get_stats(self):
        """Get push notification stats for admin dashboard."""
        return self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '24 hours') AS sends_24h,
                COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '7 days') AS sends_7d,
                COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '30 days') AS sends_30d
            FROM push_rate_limit_log
        ''')


class NotificationRepository(BaseRepository):

    # ---- Notification Settings ----

    def get_settings(self) -> dict:
        """Get all notification settings as a dictionary."""
        rows = self.query_all('SELECT setting_key, setting_value FROM notification_settings')
        return {row['setting_key']: row['setting_value'] for row in rows}

    def save_setting(self, key: str, value: str) -> bool:
        """Save or update a notification setting."""
        self.execute('''
            INSERT INTO notification_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON CONFLICT (setting_key)
            DO UPDATE SET setting_value = %s, updated_at = CURRENT_TIMESTAMP
        ''', (key, value, value))
        return True

    def save_settings_bulk(self, settings: dict) -> bool:
        """Save multiple notification settings at once."""
        def _work(cursor):
            for key, value in settings.items():
                cursor.execute('''
                    INSERT INTO notification_settings (setting_key, setting_value)
                    VALUES (%s, %s)
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = %s, updated_at = CURRENT_TIMESTAMP
                ''', (key, value, value))
        self.execute_many(_work)
        return True

    # ---- Notification Logs ----

    def log_notification(self, responsable_id: int, invoice_id: int, notification_type: str,
                         subject: str, message: str, status: str = 'pending') -> int:
        """Log a notification."""
        result = self.execute('''
            INSERT INTO notification_log (responsable_id, invoice_id, notification_type, subject, message, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (responsable_id, invoice_id, notification_type, subject, message, status), returning=True)
        return result['id']

    def update_status(self, log_id: int, status: str, error_message: str = None) -> bool:
        """Update notification log status."""
        if status == 'sent':
            rowcount = self.execute('''
                UPDATE notification_log
                SET status = %s, sent_at = CURRENT_TIMESTAMP, error_message = %s
                WHERE id = %s
            ''', (status, error_message, log_id))
        else:
            rowcount = self.execute('''
                UPDATE notification_log
                SET status = %s, error_message = %s
                WHERE id = %s
            ''', (status, error_message, log_id))
        return rowcount > 0

    def get_logs(self, limit: int = 100) -> list[dict]:
        """Get recent notification logs."""
        return self.query_all('''
            SELECT nl.*, u.name as responsable_name, u.email as responsable_email,
                   i.invoice_number, i.supplier
            FROM notification_log nl
            LEFT JOIN users u ON nl.responsable_id = u.id
            LEFT JOIN invoices i ON nl.invoice_id = i.id
            ORDER BY nl.created_at DESC
            LIMIT %s
        ''', (limit,))

    # ---- User Notifications ----

    def get_user_notifications(self, user_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
        """Get notifications sent to a user."""
        def _work(cursor):
            cursor.execute('SELECT email FROM users WHERE id = %s', (user_id,))
            user_row = cursor.fetchone()
            if not user_row or not user_row['email']:
                return []
            cursor.execute('''
                SELECT id, event_type, invoice_id, recipient_email, status,
                       error_message, created_at
                FROM notification_logs
                WHERE LOWER(recipient_email) = LOWER(%s)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            ''', (user_row['email'], limit, offset))
            from database import dict_from_row
            return [dict_from_row(dict(row)) for row in cursor.fetchall()]
        return self.execute_many(_work)

    def get_user_notifications_summary(self, user_id: int) -> dict:
        """Get notification summary for a user."""
        def _work(cursor):
            cursor.execute('SELECT email FROM users WHERE id = %s', (user_id,))
            user_row = cursor.fetchone()
            if not user_row or not user_row['email']:
                return {'total': 0, 'sent': 0, 'failed': 0}
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'sent') as sent,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed
                FROM notification_logs
                WHERE LOWER(recipient_email) = LOWER(%s)
            ''', (user_row['email'],))
            row = cursor.fetchone()
            if row:
                return {
                    'total': row['total'],
                    'sent': row['sent'],
                    'failed': row['failed'],
                }
            return {'total': 0, 'sent': 0, 'failed': 0}
        return self.execute_many(_work)
