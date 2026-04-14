"""Mobile API routes package."""

__all__ = [
    'mobile_bp',
    '_decode_token',
    '_JWT_SECRET',
    'auth',
    'devices',
    'dashboard',
    'checkin',
    'signatures',
    'version',
]

from .. import mobile_bp  # noqa: F401
from ._shared import _decode_token, _JWT_SECRET  # noqa: F401 — consumed by app.py hooks
from . import auth       # noqa: F401
from . import devices    # noqa: F401
from . import dashboard  # noqa: F401
from . import checkin    # noqa: F401
from . import signatures # noqa: F401
from . import version    # noqa: F401
