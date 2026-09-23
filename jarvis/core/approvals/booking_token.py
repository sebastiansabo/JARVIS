"""Signed one-tap token for public test-drive booking confirm/cancel links.

Encodes an action (confirm/cancel) plus the thing it acts on -- a single
booking (`bid`) OR a whole booking GROUP (`gid`, several intervals booked
together) -- signed with the app SECRET_KEY so an emailed Confirm/Cancel link
authenticates the customer's intent without a login. It is per-booking (or
per-group), time-limited, and tamper-evident. The action is still gated by each
booking's own state (pending_confirm / not expired) in the service layer.

One serializer + one salt is used for both shapes; `read_booking_token` returns
whichever key is present, so the route/service can tell a group link (`gid`
set) from a single link (`bid` set) and branch accordingly.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT = 'td-booking-action'
_ACTIONS = ('confirm', 'cancel')
DEFAULT_MAX_AGE = 7 * 24 * 3600  # 7 days


def make_booking_token(booking_id, action, secret_key):
    """Signed token for a SINGLE booking (payload {'bid', 'act'})."""
    if action not in _ACTIONS:
        return None
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({'bid': booking_id, 'act': action}, salt=_SALT)


def make_group_token(group_id, action, secret_key):
    """Signed token for a whole booking GROUP (payload {'gid', 'act'}); one link
    confirms/cancels every interval booked together."""
    if action not in _ACTIONS:
        return None
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({'gid': group_id, 'act': action}, salt=_SALT)


def read_booking_token(token, secret_key, max_age=DEFAULT_MAX_AGE):
    """Verify + decode a confirm/cancel token. Returns
    {'bid': <id|None>, 'gid': <group|None>, 'act': <action>} on success (exactly
    one of bid/gid is set), or None if the signature/age/shape is invalid."""
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(token, salt=_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get('act') not in _ACTIONS:
        return None
    if data.get('bid') is None and data.get('gid') is None:
        return None
    return {'bid': data.get('bid'), 'gid': data.get('gid'), 'act': data.get('act')}
