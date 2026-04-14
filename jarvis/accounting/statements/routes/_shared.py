"""Shared imports, helpers, and decorators for statements routes."""
import re
import logging
import time
import csv
import io
from collections import defaultdict
from functools import wraps
from datetime import date
from flask import request, jsonify, redirect, Response
from flask_login import login_required, current_user

from accounting.statements import statements_bp
from ..services import StatementsService
from core.utils.api_helpers import api_login_required
from core.roles.repositories.permission_repository import PermissionRepository

logger = logging.getLogger('jarvis.statements.routes')

# Initialize service
statements_service = StatementsService()
_perm_repo = PermissionRepository()


def statements_access_required(f):
    """Require statements.module.access V2 permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        role_id = getattr(current_user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'statements', 'module', 'access')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'Statements access denied'}), 403
        return f(*args, **kwargs)
    return decorated


# File size limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB total per request

# Rate limiting constants
MAX_BULK_ITEMS = 100  # Max items per bulk request
RATE_LIMIT_REQUESTS = 10  # Max bulk requests per window
RATE_LIMIT_WINDOW = 60  # Window in seconds (1 minute)


class RateLimiter:
    """Simple in-memory rate limiter for bulk operations."""

    def __init__(self):
        # Dict of user_id -> list of request timestamps
        self._requests = defaultdict(list)

    def is_allowed(self, user_id: int, max_requests: int = RATE_LIMIT_REQUESTS,
                   window_seconds: int = RATE_LIMIT_WINDOW) -> tuple[bool, int]:
        """
        Check if a request is allowed for this user.

        Returns:
            (is_allowed, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds

        # Clean old requests outside the window
        self._requests[user_id] = [
            ts for ts in self._requests[user_id] if ts > window_start
        ]

        if len(self._requests[user_id]) >= max_requests:
            # Calculate retry-after
            oldest_in_window = min(self._requests[user_id])
            retry_after = int(oldest_in_window + window_seconds - now) + 1
            return False, max(1, retry_after)

        # Record this request
        self._requests[user_id].append(now)
        return True, 0

    def get_remaining(self, user_id: int, max_requests: int = RATE_LIMIT_REQUESTS,
                      window_seconds: int = RATE_LIMIT_WINDOW) -> int:
        """Get remaining requests for this user in the current window."""
        now = time.time()
        window_start = now - window_seconds

        # Count requests in window
        recent = [ts for ts in self._requests[user_id] if ts > window_start]
        return max(0, max_requests - len(recent))


# Global rate limiter instance
bulk_rate_limiter = RateLimiter()


def rate_limit_bulk(f):
    """Decorator to apply rate limiting to bulk operations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = current_user.id if current_user.is_authenticated else 0

        is_allowed, retry_after = bulk_rate_limiter.is_allowed(user_id)

        if not is_allowed:
            response = jsonify({
                'success': False,
                'error': 'Rate limit exceeded',
                'details': {
                    'message': f'Too many bulk requests. Maximum {RATE_LIMIT_REQUESTS} requests per minute.',
                    'retry_after': retry_after
                }
            })
            response.status_code = 429
            response.headers['Retry-After'] = str(retry_after)
            return response

        return f(*args, **kwargs)
    return decorated_function


def validate_regex(pattern: str) -> tuple[bool, str]:
    """Validate a regex pattern. Returns (is_valid, error_message)."""
    try:
        re.compile(pattern)
        return True, None
    except re.error as e:
        return False, str(e)


def get_json_or_error():
    """Get JSON from request with null check. Returns (data, error_response)."""
    data = request.get_json()
    if data is None:
        return None, (jsonify({
            'success': False,
            'error': 'Invalid or missing JSON body',
            'details': {'body': 'Request body must be valid JSON'}
        }), 400)
    return data, None


def _validate_upload_files(files: list) -> tuple[bool, str, int]:
    """
    Validate uploaded files for size constraints.

    Returns:
        (is_valid, error_message, total_size)
    """
    total_size = 0
    for file in files:
        if not file.filename:
            continue
        # Get file size by seeking to end
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            return False, f'File {file.filename} exceeds maximum size of 10MB', 0

        total_size += file_size

    if total_size > MAX_TOTAL_SIZE:
        return False, 'Total upload size exceeds maximum of 50MB', total_size

    return True, None, total_size
