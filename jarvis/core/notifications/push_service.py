"""Firebase Cloud Messaging push notification service.

Sends push notifications to mobile devices via FCM using the
firebase-admin SDK and stored device tokens from `mobile_devices` table.

Includes a pre-send pipeline that checks:
- Global enabled flag
- Category active status
- Quiet hours (with critical bypass)
- Per-user rate limiting
- TTL and priority from category config
"""

import logging
import os
import time as _time
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.core.notifications.push_service')

_firebase_app = None


def _restore_service_account(cred_path):
    """Restore service-account.json from DB credentials if file is missing."""
    try:
        from core.connectors.repositories.connector_repository import ConnectorRepository
        connector = ConnectorRepository().get_by_type('firebase')
        if not connector:
            return False
        creds = connector.get('credentials', {})
        if isinstance(creds, str):
            import json
            creds = json.loads(creds)
        if creds and creds.get('private_key'):
            import json
            with open(cred_path, 'w') as f:
                json.dump(creds, f, indent=2)
            logger.info('Restored service-account.json from database')
            return True
    except Exception as e:
        logger.warning('Could not restore service-account.json from DB: %s', e)
    return False


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

        # If file missing, try to restore from DB
        if not os.path.exists(cred_path):
            if not _restore_service_account(cred_path):
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

    def get_active_device_count(self):
        row = self.query_one('SELECT COUNT(*) AS cnt FROM mobile_devices')
        return row['cnt'] if row else 0


_device_repo = _DeviceRepo()


# ============== Settings & Category Cache ==============

class _PushSettingsCache:
    """In-memory cache for push settings and categories (60s TTL)."""

    def __init__(self):
        self._settings = {}
        self._categories = {}  # slug -> row dict
        self._loaded_at = 0

    def get_settings(self):
        self._maybe_reload()
        return self._settings

    def get_category(self, slug):
        self._maybe_reload()
        return self._categories.get(slug)

    def get_all_categories(self):
        self._maybe_reload()
        return list(self._categories.values())

    def invalidate(self):
        self._loaded_at = 0

    def _maybe_reload(self):
        if _time.time() - self._loaded_at < 60:
            return
        try:
            from .repositories import NotificationRepository, PushCategoryRepository
            settings = NotificationRepository().get_settings()
            self._settings = {k: v for k, v in settings.items() if k.startswith('push_')}
            cats = PushCategoryRepository().get_all()
            self._categories = {c['slug']: c for c in cats}
            self._loaded_at = _time.time()
        except Exception as e:
            logger.warning('Failed to reload push settings cache: %s', e)


_cache = _PushSettingsCache()


def get_push_settings_cache():
    """Expose the cache for routes/admin use."""
    return _cache


# ============== Quiet Hours Check ==============

def _is_quiet_hours(settings):
    """Check if current time falls within quiet hours (Europe/Bucharest)."""
    if settings.get('push_quiet_hours_enabled') != 'true':
        return False
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
    except ImportError:
        return False

    tz = ZoneInfo('Europe/Bucharest')
    now = datetime.now(tz)
    current_minutes = now.hour * 60 + now.minute

    start_str = settings.get('push_quiet_hours_start', '22:00')
    end_str = settings.get('push_quiet_hours_end', '07:00')
    sh, sm = map(int, start_str.split(':'))
    eh, em = map(int, end_str.split(':'))
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes
    else:
        # Wraps midnight (e.g. 22:00 - 07:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes


# ============== Rate Limit Check ==============

def _check_rate_limits(user_ids, category_slug, category_max, global_max):
    """Filter user_ids to only those within rate limits. Returns allowed user_ids."""
    if not category_max and not global_max:
        return user_ids

    from .repositories import PushRateLimitRepository
    rate_repo = PushRateLimitRepository()
    allowed = []
    effective_max = min(
        category_max or 9999,
        global_max or 9999,
    )
    for uid in user_ids:
        count = rate_repo.count_recent(uid, category_slug, 3600)
        if count < effective_max:
            allowed.append(uid)
        else:
            logger.debug('Rate-limited push for user %d category %s (%d/%d)',
                         uid, category_slug, count, effective_max)
    return allowed


# ============== Main Send Function ==============

def send_push_to_users(user_ids, title, body, data=None, category='system', bypass_rules=False):
    """Send a push notification to all devices belonging to given user_ids.

    Args:
        user_ids: list of user IDs to notify
        title: notification title
        body: notification body text
        data: optional dict of string key-value pairs for data payload
        category: notification category slug (default 'system')
        bypass_rules: if True, skip quiet hours/rate limit/category checks (admin test sends)
    """
    if not user_ids:
        return

    settings = _cache.get_settings()
    cat_info = _cache.get_category(category)

    # --- Pre-send pipeline (skipped when bypass_rules=True) ---
    if not bypass_rules:
        # 1. Global kill-switch
        if settings.get('push_global_enabled') != 'true':
            logger.debug('Push globally disabled, skipping')
            return

        # 2. Category active check
        if cat_info and not cat_info.get('is_active', True):
            logger.debug('Push category %s is disabled, skipping', category)
            return

        # 3. Quiet hours check
        if _is_quiet_hours(settings):
            cat_priority = (cat_info or {}).get('priority', 'normal')
            allow_critical = settings.get('push_quiet_hours_allow_critical') == 'true'
            if not (allow_critical and cat_priority == 'critical'):
                logger.debug('Push blocked by quiet hours (category=%s, priority=%s)', category, cat_priority)
                return

        # 4. Rate limit check
        cat_max = (cat_info or {}).get('max_per_hour')
        global_max = None
        try:
            global_max = int(settings.get('push_global_rate_limit', '0')) or None
        except (ValueError, TypeError):
            pass
        if cat_max or global_max:
            user_ids = _check_rate_limits(list(user_ids), category, cat_max, global_max)
            if not user_ids:
                logger.debug('All users rate-limited for category %s', category)
                return

    # --- Firebase init ---
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

    # Build FCM config from category settings
    cat_priority = (cat_info or {}).get('priority', 'normal')
    fcm_priority = 'high' if cat_priority in ('critical', 'high') else 'normal'
    channel_id = (cat_info or {}).get('android_channel_id', 'default_notifications')

    ttl_seconds = (cat_info or {}).get('ttl_seconds')
    if ttl_seconds is None:
        try:
            ttl_seconds = int(settings.get('push_default_ttl', '86400'))
        except (ValueError, TypeError):
            ttl_seconds = 86400

    notification = messaging.Notification(title=title, body=body)
    android_config = messaging.AndroidConfig(
        priority=fcm_priority,
        ttl=ttl_seconds,
        notification=messaging.AndroidNotification(
            sound='default',
            channel_id=channel_id,
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
                'FCM multicast [%s]: %d success, %d failure',
                category, response.success_count, response.failure_count,
            )
        except Exception as e:
            logger.error('FCM multicast send failed: %s', e)

    # Record sends for rate limiting (only if rules were applied)
    if not bypass_rules:
        try:
            from .repositories import PushRateLimitRepository
            sent_user_ids = list({d['user_id'] for d in devices})
            PushRateLimitRepository().record_bulk(sent_user_ids, category)
        except Exception as e:
            logger.debug('Failed to record push rate limit: %s', e)
