"""Universal in-app notification helper.

Simple API for any module to send in-app notifications:

    from core.notifications.notify import notify_user, notify_users

    notify_user(user_id, 'Invoice #123 approved', link='/app/accounting')
    notify_users([1, 2, 3], 'New approval request', type='approval')
"""

import logging
from .repositories.in_app_repo import InAppNotificationRepository

logger = logging.getLogger('jarvis.core.notifications.notify')

_repo = InAppNotificationRepository()


def notify_user(user_id, title, message=None, link=None,
                entity_type=None, entity_id=None, type='info'):
    """Send an in-app notification to a single user."""
    try:
        return _repo.create(
            user_id=user_id, title=title, type=type,
            message=message, link=link,
            entity_type=entity_type, entity_id=entity_id,
        )
    except Exception as e:
        logger.error(f'Failed to create notification for user {user_id}: {e}')
        return None


def notify_users(user_ids, title, message=None, link=None,
                 entity_type=None, entity_id=None, type='info'):
    """Send the same in-app notification to multiple users."""
    if not user_ids:
        return []
    try:
        return _repo.create_bulk(
            user_ids=user_ids, title=title, type=type,
            message=message, link=link,
            entity_type=entity_type, entity_id=entity_id,
        )
    except Exception as e:
        logger.error(f'Failed to create notifications for {len(user_ids)} users: {e}')
        return []
