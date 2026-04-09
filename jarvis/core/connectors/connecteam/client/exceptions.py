"""Connecteam API client exceptions."""


class ConnecteamError(Exception):
    """Base exception for all Connecteam API errors."""

    def __init__(self, message, code=None, is_retryable=False):
        super().__init__(message)
        self.code = code
        self.is_retryable = is_retryable


class AuthenticationError(ConnecteamError):
    """OAuth token request failed or invalid credentials."""

    def __init__(self, message='Authentication failed', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)


class WebhookVerificationError(ConnecteamError):
    """Webhook signature verification failed."""

    def __init__(self, message='Webhook verification failed', **kwargs):
        super().__init__(message, is_retryable=False, **kwargs)


class NetworkError(ConnecteamError):
    """Connection refused, timeout, or network issue."""

    def __init__(self, message='Network error', **kwargs):
        super().__init__(message, is_retryable=True, **kwargs)


class TimeoutError(NetworkError):
    """Request timed out."""

    def __init__(self, message='Request timed out', **kwargs):
        super().__init__(message, **kwargs)


class APIError(ConnecteamError):
    """Non-success response from Connecteam API."""

    def __init__(self, message='API error', status_code=None, **kwargs):
        is_retryable = status_code and status_code >= 500
        super().__init__(message, is_retryable=is_retryable, **kwargs)
        self.status_code = status_code
