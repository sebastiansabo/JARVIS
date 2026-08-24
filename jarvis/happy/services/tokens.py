"""Impression tokens — signed, TTL-bounded proof that the server showed an item.

Event POSTs are rejected without a valid token, preventing client-side inflation
of read/ack analytics (which feed a legally-consequential compliance report, §4).
"""
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT = "happy-impression-v1"
_DEFAULT_TTL = 600  # 10 minutes (spec §4)


def _secret():
    return (
        os.environ.get("SECRET_KEY")
        or os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("JWT_SECRET_KEY")
        or "happy-dev-secret-change-me"
    )


def _serializer():
    return URLSafeTimedSerializer(_secret(), salt=_SALT)


def mint_impression_token(campaign_id, user_id, surface):
    return _serializer().dumps({"c": campaign_id, "u": user_id, "s": surface})


def verify_impression_token(token, max_age=_DEFAULT_TTL):
    """Return {campaign_id, user_id, surface} or None if invalid/expired."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return {"campaign_id": data.get("c"), "user_id": data.get("u"), "surface": data.get("s")}
