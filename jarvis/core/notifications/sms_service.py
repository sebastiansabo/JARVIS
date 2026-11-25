"""SMS delivery via smsapi.com (EU/RO).

Opt-in per-category channel with a fail-CLOSED gate (never blast billed SMS on a
DB error) and a mock mode for dev/test. Real sends happen only when SMSAPI_TOKEN
is configured AND SMS_MOCK_MODE is not 'true' — so prod stays in mock mode until
the token is deliberately set.

Env:
  SMSAPI_TOKEN   - smsapi.com OAuth bearer token (absent => mock mode)
  SMSAPI_FROM    - registered sender id (default 'JARVIS')
  SMS_MOCK_MODE  - 'true' forces mock mode even with a token
"""
import os
import re
import logging

logger = logging.getLogger('jarvis.core.notifications.sms')

_SMSAPI_URL = 'https://api.smsapi.com/sms.do'


def normalize_ro_phone(raw):
    """Normalize a Romanian mobile number to E.164 (+40 7xxxxxxxx), or None.

    Accepts local (07...), spaced, +40, 0040 and bare 9-digit forms; rejects
    landlines and anything that isn't a plausible RO mobile.
    """
    if not raw:
        return None
    digits = re.sub(r'\D', '', str(raw))
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('40'):
        rest = digits[2:]
    elif digits.startswith('0'):
        rest = digits[1:]
    else:
        rest = digits
    if len(rest) == 9 and rest.startswith('7'):
        return '+40' + rest
    return None


def _mock_mode():
    if os.environ.get('SMS_MOCK_MODE', '').lower() == 'true':
        return True
    return not os.environ.get('SMSAPI_TOKEN')


def send_sms_to_users(user_ids, body, category='system', bypass_rules=False):
    """Send an SMS to users opted into the 'sms' channel for this category.

    Mandatory categories force delivery to everyone (no query). The gate is
    fail-closed: on a lookup error we send nothing rather than risk a billed
    blast. Users without a valid RO mobile are skipped; numbers are deduped.
    """
    if not user_ids:
        return
    from .categories import is_mandatory

    recipients = list(user_ids)
    if not bypass_rules and not is_mandatory(category):
        try:
            from .repositories import UserNotificationPreferenceRepository
            recipients = UserNotificationPreferenceRepository().preference_filter(
                recipients, category, 'sms')
        except Exception as e:
            logger.error('SMS gate failed (%s); sending nothing (fail-closed): %s', category, e)
            return
    if not recipients:
        return

    try:
        from .repositories import UserNotificationPreferenceRepository
        contacts = UserNotificationPreferenceRepository().get_contacts(recipients)
    except Exception as e:
        logger.error('SMS contact lookup failed (%s): %s', category, e)
        return

    phones, seen = [], set()
    for uid in recipients:
        ph = normalize_ro_phone((contacts.get(uid) or {}).get('phone'))
        if ph and ph not in seen:
            seen.add(ph)
            phones.append(ph)
    if not phones:
        return
    _dispatch(phones, body)


def _dispatch(phones, body):
    if _mock_mode():
        logger.info('[SMS MOCK] %d recipient(s): %s', len(phones), (body or '')[:80])
        return 'mock'
    return _post_smsapi(phones, body)


def _post_smsapi(phones, body):
    token = os.environ.get('SMSAPI_TOKEN')
    sender = os.environ.get('SMSAPI_FROM', 'JARVIS')
    try:
        import requests
    except ImportError:
        logger.error('requests unavailable; cannot send SMS')
        return None
    sent = 0
    for ph in phones:
        try:
            resp = requests.post(
                _SMSAPI_URL,
                headers={'Authorization': f'Bearer {token}'},
                data={'to': ph, 'message': body, 'from': sender,
                      'format': 'json', 'encoding': 'utf-8'},
                timeout=10,
            )
            if resp.status_code == 200 and 'error' not in (resp.text or '').lower():
                sent += 1
            else:
                logger.warning('SMS to %s failed: %s %s', ph, resp.status_code, (resp.text or '')[:120])
        except Exception as e:
            logger.error('SMS to %s error: %s', ph, e)
    return sent
