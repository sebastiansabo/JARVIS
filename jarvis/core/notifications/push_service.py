"""Firebase Cloud Messaging push notification service.

Sends push notifications to mobile devices via FCM using the
firebase-admin SDK and stored device tokens from `mobile_devices` table.
"""

import logging
import os
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.notifications.push_service')

_firebase_app = None


def _init_firebase():
    """Lazily initialise Firebase Admin SDK."""
    global _firebase_app
    if _firebase_app is not None:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', '..', 'service-account.json',
        )
        cred_path = os.path.normpath(cred_path)
        if not os.path.exists(cred_path):
            logger.warning('Firebase service-account.json not found at %s', cred_path)
            return False

        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info('Firebase Admin SDK initialised (project: %s)', cred.project_id)
        return True
    except Exception as e:
        logger.error('Failed to initialise Firebase Admin SDK: %s', e)
        return False


class _DeviceRepo(BaseRepository):
    """Thin helper to query mobile_devices table."""

    def get_tokens_for_users(self, user_ids):
        if not user_ids:
            return []
        placeholders = ','.join(['%s'] * len(user_ids))
        return self.query_all(
            f'SELECT id, user_id, push_token FROM mobile_devices WHERE user_id IN ({placeholders})',
            tuple(user_ids),
        )

    def delete_tokens(self, token_ids):
        if not token_ids:
            return
        placeholders = ','.join(['%s'] * len(token_ids))
        self.execute(
            f'DELETE FROM mobile_devices WHERE id IN ({placeholders})',
            tuple(token_ids),
        )


_device_repo = _DeviceRepo()


def send_push_to_users(user_ids, title, body, data=None):
    """Send a push notification to all devices belonging to given user_ids.

    Args:
        user_ids: list of user IDs to notify
        title: notification title
        body: notification body text
        data: optional dict of string key-value pairs for data payload
    """
    if not user_ids:
        return

    if not _init_firebase():
        logger.warning('Firebase not available, skipping push notification')
        return

    try:
        from firebase_admin import messaging
    except ImportError:
        logger.error('firebase_admin.messaging not available')
        return

    devices = _device_repo.get_tokens_for_users(user_ids)
    if not devices:
        return

    tokens = [d['push_token'] for d in devices]
    token_id_map = {d['push_token']: d['id'] for d in devices}

    notification = messaging.Notification(title=title, body=body)
    android_config = messaging.AndroidConfig(
        priority='high',
        notification=messaging.AndroidNotification(
            sound='default',
            channel_id='digest_notifications',
        ),
    )

    # FCM supports max 500 tokens per multicast
    for i in range(0, len(tokens), 500):
        batch_tokens = tokens[i:i + 500]
        message = messaging.MulticastMessage(
            notification=notification,
            data=data or {},
            tokens=batch_tokens,
            android=android_config,
        )

        try:
            response = messaging.send_each_for_multicast(message)
            # Clean up invalid tokens
            failed_ids = []
            for idx, send_response in enumerate(response.responses):
                if send_response.exception is not None:
                    error_code = getattr(send_response.exception, 'code', '')
                    if error_code in ('NOT_FOUND', 'UNREGISTERED', 'INVALID_ARGUMENT'):
                        failed_token = batch_tokens[idx]
                        if failed_token in token_id_map:
                            failed_ids.append(token_id_map[failed_token])
                    logger.debug('FCM send failed for token: %s', send_response.exception)

            if failed_ids:
                _device_repo.delete_tokens(failed_ids)
                logger.info('Removed %d invalid push tokens', len(failed_ids))

            logger.info(
                'FCM multicast: %d success, %d failure',
                response.success_count, response.failure_count,
            )
        except Exception as e:
            logger.error('FCM multicast send failed: %s', e)
