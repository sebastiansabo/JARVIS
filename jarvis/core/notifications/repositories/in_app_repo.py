"""In-app notification repository.

Handles CRUD for the `notifications` table — universal notification center
used by all modules (approvals, invoices, e-Factura, HR, statements, etc.).
"""

import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.notifications.in_app_repo')


class InAppNotificationRepository:

    def create(self, user_id, title, type='info', message=None, link=None,
               entity_type=None, entity_id=None):
        """Create a notification for a user. Returns notification id."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO notifications (user_id, type, title, message, link, entity_type, entity_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (user_id, type, title, message, link, entity_type, entity_id))
            nid = cursor.fetchone()['id']
            conn.commit()
            return nid
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def create_bulk(self, user_ids, title, type='info', message=None, link=None,
                    entity_type=None, entity_id=None):
        """Create the same notification for multiple users."""
        if not user_ids:
            return []
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            ids = []
            for uid in user_ids:
                cursor.execute('''
                    INSERT INTO notifications (user_id, type, title, message, link, entity_type, entity_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (uid, type, title, message, link, entity_type, entity_id))
                ids.append(cursor.fetchone()['id'])
            conn.commit()
            return ids
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def get_for_user(self, user_id, limit=20, offset=0, unread_only=False):
        """Get notifications for a user, newest first."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            where = 'WHERE user_id = %s'
            params = [user_id]
            if unread_only:
                where += ' AND is_read = FALSE'
            cursor.execute(f'''
                SELECT * FROM notifications
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            ''', (*params, limit, offset))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_unread_count(self, user_id):
        """Get count of unread notifications."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'SELECT COUNT(*) as cnt FROM notifications WHERE user_id = %s AND is_read = FALSE',
                (user_id,)
            )
            return cursor.fetchone()['cnt']
        finally:
            release_db(conn)

    def mark_read(self, notification_id, user_id):
        """Mark a single notification as read. Returns True if updated."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s',
                (notification_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def mark_all_read(self, user_id):
        """Mark all notifications as read for a user. Returns count updated."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE',
                (user_id,)
            )
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def delete_old(self, days=30):
        """Delete notifications older than N days. Returns count deleted."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                "DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '%s days'",
                (days,)
            )
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)
