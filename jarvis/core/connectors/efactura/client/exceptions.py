"""
e-Factura Custom Exceptions

Defines exception hierarchy for ANAF API errors.
"""

from typing import Optional, Dict, Any


class ANAFError(Exception):
    """Base exception for all ANAF API errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.is_retryable = is_retryable

    def __str__(self) -> str:
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class AuthenticationError(ANAFError):
    """Raised when authentication with ANAF fails."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code or "AUTH_ERROR",
            details=details,
            is_retryable=False,  # Auth errors typically need manual intervention
        )


class CertificateError(ANAFError):
    """Raised for certificate-related issues."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=code or "CERT_ERROR",
            details=details,
            is_retryable=False,
        )


class CertificateExpiredError(CertificateError):
    """Raised when certificate has expired."""

    def __init__(self, expires_at: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Certificate expired at {expires_at}",
            code="CERT_EXPIRED",
            details={"expires_at": expires_at, **(details or {})},
        )


class CertificateExpiringError(CertificateError):
    """Raised as warning when certificate is expiring soon."""

    def __init__(
        self, days_remaining: int, details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=f"Certificate expires in {days_remaining} days",
            code="CERT_EXPIRING",
            details={"days_remaining": days_remaining, **(details or {})},
        )


class RateLimitError(ANAFError):
    """Raised when ANAF rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        super().__init__(
            message=message,
            code="RATE_LIMIT",
            details={"retry_after": retry_after, **(details or {})},
            is_retryable=True,
        )


class ValidationError(ANAFError):
    """Raised when ANAF rejects a request due to validation failure."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.field = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field, **(details or {})},
            is_retryable=False,
        )


class NetworkError(ANAFError):
    """Raised for network-level failures."""

    def __init__(
        self,
        message: str = "Network error",
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.original_error = original_error
        super().__init__(
            message=message,
            code="NETWORK_ERROR",
            details={
                "original_error": str(original_error) if original_error else None,
                **(details or {}),
            },
            is_retryable=True,
        )


class TimeoutError(NetworkError):
    """Raised when request times out."""

    def __init__(
        self,
        message: str = "Request timed out",
        timeout_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            details={"timeout_seconds": timeout_seconds, **(details or {})},
        )
        self.code = "TIMEOUT"


class APIError(ANAFError):
    """Raised for ANAF API-level errors (non-200 responses)."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.response_body = response_body

        # Determine if retryable based on status code
        is_retryable = status_code in (500, 502, 503, 504)

        super().__init__(
            message=message,
            code=f"API_ERROR_{status_code}",
            details={
                "status_code": status_code,
                "response_body_hash": self._hash_body(response_body),
                **(details or {}),
            },
            is_retryable=is_retryable,
        )

    @staticmethod
    def _hash_body(body: Optional[str]) -> Optional[str]:
        """Hash response body for logging without exposing content."""
        if not body:
            return None
        import hashlib
        return hashlib.sha256(body.encode()).hexdigest()[:16]


class ParseError(ANAFError):
    """Raised when parsing ANAF response fails."""

    def __init__(
        self,
        message: str,
        content_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="PARSE_ERROR",
            details={"content_type": content_type, **(details or {})},
            is_retryable=False,
        )


class InvoiceNotFoundError(ANAFError):
    """Raised when requested invoice/message is not found."""

    def __init__(
        self,
        message_id: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=f"Invoice/message not found: {message_id}",
            code="NOT_FOUND",
            details={"message_id": message_id, **(details or {})},
            is_retryable=False,
        )
