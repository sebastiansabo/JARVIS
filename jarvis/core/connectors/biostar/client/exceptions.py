"""BioStar 2 API client exceptions."""


class BioStarError(Exception):
    """Base exception for all BioStar API errors."""

    def __init__(self, message, code=None, details=None, is_retryable=False):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.is_retryable = is_retryable


class AuthenticationError(BioStarError):
    """Login failures or invalid credentials."""

    def __init__(self, message='Authentication failed', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)


class SessionExpiredError(AuthenticationError):
    """Session ID expired — need to re-login."""

    def __init__(self, message='Session expired', **kwargs):
        super().__init__(message, **kwargs)


class NetworkError(BioStarError):
    """Connection refused, timeout, or network issue."""

    def __init__(self, message='Network error', **kwargs):
        super().__init__(message, is_retryable=True, **kwargs)


class TimeoutError(NetworkError):
    """Request timed out."""

    def __init__(self, message='Request timed out', **kwargs):
        super().__init__(message, **kwargs)


class APIError(BioStarError):
    """Non-success response from BioStar API."""

    def __init__(self, message='API error', status_code=None, **kwargs):
        is_retryable = status_code and status_code >= 500
        super().__init__(message, is_retryable=is_retryable, **kwargs)
        self.status_code = status_code


class ParseError(BioStarError):
    """Failed to parse API response."""

    def __init__(self, message='Failed to parse response', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)
