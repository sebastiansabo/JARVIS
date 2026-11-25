"""Universal in-app notification helper.

Simple API for any module to send in-app notifications:

    from core.notifications.notify import notify_user, notify_users

    notify_user(user_id, 'Invoice #123 approved', link='/app/accounting')
    notify_users([1, 2, 3], 'New approval request', type='approval')

For in-app + push:

    from core.notifications.notify import notify_with_push

    notify_with_push([1, 2, 3], 'New announcement', message='...', push_data={'channel_id': '5'})
"""

import logging
from .repositories.in_app_repo import InAppNotificationRepository

logger = logging.getLogger('jarvis.core.notifications.notify')

_repo = InAppNotificationRepository()


def _gate(user_ids, category, channel):
    """Recipients allowed to receive ``category`` on ``channel`` per their
    per-user preferences. Fails open (returns everyone) on any error so a
    preference-table hiccup never silently drops notifications."""
    try:
        from .repositories import UserNotificationPreferenceRepository
        return UserNotificationPreferenceRepository().preference_filter(
            list(user_ids), category, channel)
    except Exception as e:
        logger.error(
            f'notification preference gate failed ({channel}/{category}); '
            f'delivering to all: {e}')
        return list(user_ids)


def notify_user(user_id, title, message=None, link=None,
                entity_type=None, entity_id=None, type='info',
                category='system'):
    """Send an in-app notification + push to a single user."""
    result = None
    # In-app gate: only insert if the user hasn't disabled in-app for this category.
    if _gate([user_id], category, 'in_app'):
        try:
            result = _repo.create(
                user_id=user_id, title=title, type=type,
                message=message, link=link,
                entity_type=entity_type, entity_id=entity_id,
            )
        except Exception as e:
            logger.error(f'Failed to create notification for user {user_id}: {e}')

    # Push goes to the user regardless of the in-app choice — push has its own
    # gate inside send_push_to_users (a user may want push but not the bell feed).
    try:
        from .push_service import send_push_to_users
        send_push_to_users([user_id], title, message or title, category=category)
    except Exception as e:
        logger.debug(f'Push notification skipped for user {user_id}: {e}')

    return result


def notify_users(user_ids, title, message=None, link=None,
                 entity_type=None, entity_id=None, type='info',
                 category='system', send_push=True):
    """Send the same in-app notification to multiple users.

    By default also fires an FCM push. Callers that send their own push
    afterwards (e.g. ``notify_with_push``, which attaches a data payload)
    pass ``send_push=False`` so the user doesn't receive two pushes.
    """
    if not user_ids:
        return []
    results = []
    # In-app gate: insert only for users who haven't disabled in-app for this
    # category. Push below still targets the full list (its own gate applies).
    in_app_ids = _gate(user_ids, category, 'in_app')
    if in_app_ids:
        try:
            results = _repo.create_bulk(
                user_ids=in_app_ids, title=title, type=type,
                message=message, link=link,
                entity_type=entity_type, entity_id=entity_id,
            )
        except Exception as e:
            logger.error(f'Failed to create notifications for {len(in_app_ids)} users: {e}')

    # Also send push notification (unless the caller sends its own)
    if send_push:
        try:
            from .push_service import send_push_to_users
            send_push_to_users(list(user_ids), title, message or title, category=category)
        except Exception as e:
            logger.debug(f'Push notifications skipped for {len(user_ids)} users: {e}')

    return results


def notify_with_push(user_ids, title, message=None, link=None,
                     entity_type=None, entity_id=None, type='info',
                     push_data=None, category='system'):
    """Send in-app notifications AND FCM push to multiple users.

    Args:
        push_data: optional dict of string key-value pairs sent as FCM data payload
                   (e.g. {'channel_id': '5', 'type': 'announcement'})
        category: notification category slug for push pipeline (default 'system')
    """
    if not user_ids:
        return []

    # In-app notifications — suppress its push; we send our own below with
    # the data payload attached (avoids a duplicate FCM push per call).
    results = notify_users(user_ids, title, message, link, entity_type, entity_id, type,
                           category=category, send_push=False)

    # Push notifications (fire-and-forget, never block the request)
    try:
        from .push_service import send_push_to_users
        push_body = message or title
        send_push_to_users(list(user_ids), title, push_body, data=push_data, category=category)
    except Exception as e:
        logger.error(f'Failed to send push notifications: {e}')

    return results


def notify_node_cascade(node_id, title, message=None, link=None,
                        entity_type=None, entity_id=None, type='info',
                        category='system'):
    """Notify all responsables at a node AND all parent nodes up the chain.

    Walks the structure_nodes parent hierarchy collecting responsable user IDs,
    then sends a single bulk notification to all of them.
    """
    try:
        from core.organization.repositories import StructureNodeRepository
        user_ids = StructureNodeRepository().get_cascade_responsable_ids(node_id)
        if user_ids:
            return notify_users(user_ids, title, message, link,
                                entity_type, entity_id, type, category=category)
    except Exception as e:
        logger.error(f'Failed cascade notification for node {node_id}: {e}')
    return []
