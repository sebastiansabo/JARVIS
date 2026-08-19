"""Signed one-tap approval-action token for email decide links.

A token encodes (request_id, approver_id, action) signed with the app SECRET_KEY,
so an emailed Approve/Reject link authenticates the decision without a login. It is
per-approver, time-limited (default 7 days), and tamper-evident. The decision itself
is still gated by ApprovalEngine.decide (authorization / no-self / no-double-decide),
so the token only asserts "this approver clicked this action from their email".
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT = 'approval-email-action'
_ACTIONS = ('approve', 'reject')
DEFAULT_MAX_AGE = 7 * 24 * 3600  # 7 days


def make_action_token(request_id, approver_id, action, secret_key):
    """Sign an {rid, uid, act} token. Called internally with a valid action."""
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({'rid': request_id, 'uid': approver_id, 'act': action}, salt=_SALT)


def read_action_token(token, secret_key, max_age=DEFAULT_MAX_AGE):
    """Return {'rid','uid','act'} or None if invalid / expired / tampered / bogus action."""
    s = URLSafeTimedSerializer(secret_key)
    try:
        data = s.loads(token, salt=_SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get('act') not in _ACTIONS:
        return None
    return {'rid': data.get('rid'), 'uid': data.get('uid'), 'act': data.get('act')}
