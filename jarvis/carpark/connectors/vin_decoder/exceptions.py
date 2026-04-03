"""Exception hierarchy for VIN decoder connector.

All exceptions inherit from VINDecoderError and carry:
- message: human-readable error description
- code: machine-readable error code for frontend
- details: dict with additional context (never contains secrets)
- is_retryable: whether the operation can be retried
"""


class VINDecoderError(Exception):
    """Base exception for all VIN decoder errors."""

    def __init__(self, message: str, code: str = None, details: dict = None,
                 is_retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.is_retryable = is_retryable

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class AuthenticationError(VINDecoderError):
    """Invalid API key or unauthorized."""

    def __init__(self, message: str = 'Authentication failed', **kwargs):
        super().__init__(message, code='AUTH_ERROR', is_retryable=False, **kwargs)


class RateLimitError(VINDecoderError):
    """API rate limit exceeded."""

    def __init__(self, message: str = 'Rate limit exceeded',
                 retry_after: int = None, **kwargs):
        self.retry_after = retry_after
        details = kwargs.pop('details', {})
        details['retry_after'] = retry_after
        super().__init__(message, code='RATE_LIMIT', is_retryable=True,
                         details=details, **kwargs)


class QuotaExhaustedError(RateLimitError):
    """Monthly/daily API quota fully consumed."""

    def __init__(self, message: str = 'API quota exhausted',
                 remaining: int = 0, **kwargs):
        super().__init__(message, **kwargs)
        self.code = 'QUOTA_EXHAUSTED'
        self.remaining = remaining


class VINNotFoundError(VINDecoderError):
    """VIN not found in provider database."""

    def __init__(self, vin: str, **kwargs):
        super().__init__(
            f'VIN not found: {vin}',
            code='VIN_NOT_FOUND',
            is_retryable=False,
            details={'vin': vin},
            **kwargs,
        )


class VINValidationError(VINDecoderError):
    """VIN format invalid (not 17 chars, bad check digit, etc.)."""

    def __init__(self, vin: str, reason: str = 'Invalid VIN format', **kwargs):
        super().__init__(
            reason,
            code='VIN_INVALID',
            is_retryable=False,
            details={'vin': vin, 'reason': reason},
            **kwargs,
        )


class NetworkError(VINDecoderError):
    """Connection failure to provider API."""

    def __init__(self, message: str = 'Network error',
                 original_error: Exception = None, **kwargs):
        details = kwargs.pop('details', {})
        details['original_error'] = str(original_error) if original_error else None
        super().__init__(message, code='NETWORK_ERROR', is_retryable=True,
                         details=details, **kwargs)


class TimeoutError(NetworkError):
    """Request timed out."""

    def __init__(self, message: str = 'Request timed out',
                 timeout_seconds: int = None, **kwargs):
        super().__init__(message, **kwargs)
        self.code = 'TIMEOUT'
        self.timeout_seconds = timeout_seconds


class APIError(VINDecoderError):
    """Non-success HTTP response from provider."""

    def __init__(self, message: str, status_code: int,
                 response_body: str = None, **kwargs):
        self.status_code = status_code
        self.response_body = response_body
        is_retryable = status_code in (500, 502, 503, 504)
        super().__init__(
            message,
            code=f'API_ERROR_{status_code}',
            is_retryable=is_retryable,
            **kwargs,
        )


class ParseError(VINDecoderError):
    """Failed to parse API response."""

    def __init__(self, message: str = 'Failed to parse response', **kwargs):
        super().__init__(message, code='PARSE_ERROR', is_retryable=False, **kwargs)


class ProviderUnavailableError(VINDecoderError):
    """All configured providers failed."""

    def __init__(self, providers_tried: list, errors: list, **kwargs):
        msg = f"All VIN providers failed: {', '.join(providers_tried)}"
        super().__init__(
            msg,
            code='ALL_PROVIDERS_FAILED',
            is_retryable=False,
            details={
                'providers': providers_tried,
                'errors': [str(e) for e in errors],
            },
            **kwargs,
        )
