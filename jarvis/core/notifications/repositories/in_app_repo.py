"""In-app notification repository.

Handles CRUD for the `notifications` table — universal notification center
used by all modules (approvals, invoices, e-Factura, HR, statements, etc.).
"""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.notifications.in_app_repo')


class InAppNotificationRepository(BaseRepository):

    def create(self, user_id, title, type='info', message=None, link=None,
               entity_type=None, entity_id=None):
        """Create a notification for a user. Returns notification id."""
        row = self.execute('''
            INSERT INTO notifications (user_id, type, title, message, link, entity_type, entity_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (user_id, type, title, message, link, entity_type, entity_id), returning=True)
        return row['id'] if row else None

    def create_bulk(self, user_ids, title, type='info', message=None, link=None,
                    entity_type=None, entity_id=None):
        """Create the same notification for multiple users."""
        if not user_ids:
            return []
        def _work(cursor):
            ids = []
            for uid in user_ids:
                cursor.execute('''
                    INSERT INTO notifications (user_id, type, title, message, link, entity_type, entity_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (uid, type, title, message, link, entity_type, entity_id))
                ids.append(cursor.fetchone()['id'])
            return ids
        return self.execute_many(_work)

    def get_for_user(self, user_id, limit=20, offset=0, unread_only=False):
        """Get notifications for a user, newest first."""
        where = 'WHERE user_id = %s'
        params = [user_id]
        if unread_only:
            where += ' AND is_read = FALSE'
        params.extend([limit, offset])
        return self.query_all(f'''
            SELECT * FROM notifications
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        ''', params)

    def get_unread_count(self, user_id):
        """Get count of unread notifications."""
        row = self.query_one(
            'SELECT COUNT(*) as cnt FROM notifications WHERE user_id = %s AND is_read = FALSE',
            (user_id,)
        )
        return row['cnt'] if row else 0

    def mark_read(self, notification_id, user_id):
        """Mark a single notification as read. Returns True if updated."""
        return self.execute(
            'UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s',
            (notification_id, user_id)
        ) > 0

    def mark_all_read(self, user_id):
        """Mark all notifications as read for a user. Returns count updated."""
        return self.execute(
            'UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE',
            (user_id,)
        )

    def delete_old(self, days=30):
        """Delete notifications older than N days. Returns count deleted."""
        return self.execute(
            "DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '%s days'",
            (days,)
        )
