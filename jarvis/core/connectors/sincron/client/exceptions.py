"""Sincron API client exceptions."""


class SincronError(Exception):
    """Base exception for all Sincron API errors."""

    def __init__(self, message, code=None, is_retryable=False):
        super().__init__(message)
        self.code = code
        self.is_retryable = is_retryable


class AuthenticationError(SincronError):
    """Invalid or expired Bearer token."""

    def __init__(self, message='Authentication failed', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)


class ValidationError(SincronError):
    """422 — missing or invalid request parameters."""

    def __init__(self, message='Validation error', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)


class NetworkError(SincronError):
    """Connection refused, timeout, or network issue."""

    def __init__(self, message='Network error', **kwargs):
        super().__init__(message, is_retryable=True, **kwargs)


class TimeoutError(NetworkError):
    """Request timed out."""

    def __init__(self, message='Request timed out', **kwargs):
        super().__init__(message, **kwargs)


class APIError(SincronError):
    """Non-success response from Sincron API."""

    def __init__(self, message='API error', status_code=None, **kwargs):
        is_retryable = status_code and status_code >= 500
        super().__init__(message, is_retryable=is_retryable, **kwargs)
        self.status_code = status_code
