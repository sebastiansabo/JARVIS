"""Shared API utilities — decorators, error helpers, rate limiter, request validation.

Consolidates patterns from across the codebase into one reusable module.
"""
import time
import logging
from collections import defaultdict
from functools import wraps

from flask import jsonify, request
from flask_login import current_user

logger = logging.getLogger('jarvis.api')


# ============== Decorators ==============

def admin_required(f):
    """Decorator requiring authentication + can_access_settings (admin) permission.

    Replaces the inline pattern:
        if not current_user.can_access_settings:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not current_user.can_access_settings:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    """Like @login_required but returns JSON 401 instead of redirect.

    Deduplicated from statements/routes.py and efactura/routes.py.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


# ============== Request Validation ==============

def get_json_or_error():
    """Get JSON from request body with null check.

    Returns (data, error_response) tuple. Caller pattern:
        data, error = get_json_or_error()
        if error:
            return error

    Lifted from statements/routes.py get_json_or_error().
    """
    data = request.get_json()
    if data is None:
        return None, (jsonify({
            'success': False,
            'error': 'Invalid or missing JSON body',
        }), 400)
    return data, None


# ============== Error Handling ==============

def safe_error_response(e, status_code=500):
    """Return error response without leaking DB internals.

    - ValueError/KeyError: returns str(e) as 400 (business validation, safe to expose)
    - Everything else: logs full exception, returns generic message
    """
    if isinstance(e, (ValueError, KeyError)):
        return jsonify({'success': False, 'error': str(e)}), 400

    logger.exception('Unhandled error in API route')
    return jsonify({'success': False, 'error': 'An internal error occurred'}), status_code


# ============== Rate Limiter ==============

class RateLimiter:
    """Simple in-memory rate limiter.

    Per-worker state (3 gunicorn workers = 3 separate states).
    Acceptable for internal tooling — not for public-facing APIs.

    Generalized from statements/routes.py RateLimiter.
    """

    def __init__(self):
        self._requests = defaultdict(list)

    def is_allowed(self, key, max_requests=10, window_seconds=60):
        """Check if request is allowed.

        Args:
            key: String identifier (user_id, IP address, etc.)
            max_requests: Max requests per window
            window_seconds: Window duration in seconds

        Returns:
            (is_allowed: bool, retry_after: int) tuple
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old entries
        self._requests[key] = [ts for ts in self._requests[key] if ts > window_start]

        if len(self._requests[key]) >= max_requests:
            oldest = min(self._requests[key])
            retry_after = int(oldest + window_seconds - now) + 1
            return False, max(1, retry_after)

        self._requests[key].append(now)
        return True, 0
