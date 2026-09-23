"""Signed one-tap token for public test-drive booking confirm/cancel links.

Encodes (booking_id, action) signed with the app SECRET_KEY so an emailed
Confirm/Cancel link authenticates the customer's intent without a login. It is
per-booking, time-limited, and tamper-evident. The action is still gated by the
booking's own state (pending_confirm / not expired) in the service layer.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT = 'td-booking-action'
_ACTIONS = ('confirm', 'cancel')
DEFAULT_MAX_AGE = 7 * 24 * 3600  # 7 days


def make_booking_token(booking_id, action, secret_key):
    if action not in _ACTIONS:
        return None
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({'bid': booking_id, 'act': action}, salt=_SALT)


def read_booking_token(token, secret_key, max_age=DEFAULT_MAX_AGE):
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(token, salt=_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get('act') not in _ACTIONS:
        return None
    return {'bid': data.get('bid'), 'act': data.get('act')}
