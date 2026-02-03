"""
ANAF e-Factura OAuth Client

HTTP client for ANAF's e-Factura REST API with OAuth2 Bearer token authentication.
Used when users authenticate via browser with USB token.

This is a core connector - available across all JARVIS sections.
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.utils.logging_config import get_logger
from .exceptions import (
    ANAFError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    TimeoutError,
    APIError,
    ParseError,
    InvoiceNotFoundError,
)
from ..config import ANAFConfig, DEFAULT_CONFIG, Environment
from ..services.oauth_service import OAuthTokens, get_oauth_service

logger = get_logger('jarvis.core.connectors.efactura.oauth_client')


@dataclass
class RateLimitState:
    """Tracks rate limit usage."""
    requests_made: int = 0
    window_start: datetime = None
    window_hours: int = 1

    def __post_init__(self):
        if self.window_start is None:
            self.window_start = datetime.now()

    def record_request(self):
        """Record a request, resetting window if needed."""
        now = datetime.now()
        if now - self.window_start > timedelta(hours=self.window_hours):
            self.requests_made = 0
            self.window_start = now
        self.requests_made += 1

    def get_remaining(self, max_requests: int) -> int:
        """Get remaining requests in current window."""
        now = datetime.now()
        if now - self.window_start > timedelta(hours=self.window_hours):
            return max_requests
        return max(0, max_requests - self.requests_made)

    def is_near_limit(self, max_requests: int, buffer: int = 10) -> bool:
        """Check if approaching rate limit."""
        return self.get_remaining(max_requests) <= buffer


class ANAFOAuthClient:
    """
    Client for ANAF e-Factura REST API using OAuth2 Bearer tokens.

    Uses OAuth2 access tokens obtained through browser authentication
    with USB token. Implements auto-refresh, rate limiting, and retries.
    """

    def __init__(
        self,
        company_cif: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        environment: Environment = Environment.PRODUCTION,
        config: Optional[ANAFConfig] = None,
    ):
        """
        Initialize OAuth ANAF client.

        Args:
            company_cif: Company CIF (used as client_id for refresh)
            access_token: OAuth access token (optional if loading from DB)
            refresh_token: OAuth refresh token (for auto-refresh)
            expires_at: Token expiration time
            environment: API environment (test or production)
            config: Optional custom configuration
        """
        self.company_cif = company_cif
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._expires_at = expires_at
        self.environment = environment
        self.config = config or DEFAULT_CONFIG

        self.base_url = self.config.get_base_url(environment)
        self._session: Optional[requests.Session] = None
        self._rate_limit = RateLimitState()

    @classmethod
    def from_stored_tokens(
        cls,
        company_cif: str,
        environment: Environment = Environment.PRODUCTION,
        config: Optional[ANAFConfig] = None,
    ) -> 'ANAFOAuthClient':
        """
        Create client from tokens stored in database.

        Args:
            company_cif: Company CIF
            environment: API environment
            config: Optional custom configuration

        Returns:
            ANAFOAuthClient instance

        Raises:
            AuthenticationError: If no tokens found for CIF
        """
        from database import get_efactura_oauth_tokens

        tokens = get_efactura_oauth_tokens(company_cif)

        if not tokens:
            raise AuthenticationError(
                f"No OAuth tokens found for CIF {company_cif}. Please authenticate first.",
                code="NO_TOKENS",
            )

        expires_at = None
        if tokens.get('expires_at'):
            expires_at_str = tokens['expires_at']
            if isinstance(expires_at_str, str):
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace('Z', '+00:00').replace('+00:00', '')
                )

        return cls(
            company_cif=company_cif,
            access_token=tokens['access_token'],
            refresh_token=tokens.get('refresh_token'),
            expires_at=expires_at,
            environment=environment,
            config=config,
        )

    def _is_token_expired(self) -> bool:
        """Check if access token is expired or about to expire."""
        if not self._expires_at:
            return False

        # Add buffer before expiry
        buffer = timedelta(seconds=self.config.OAUTH_TOKEN_EXPIRY_BUFFER)
        return datetime.utcnow() >= (self._expires_at - buffer)

    def _refresh_token_if_needed(self):
        """Auto-refresh access token if expired."""
        if not self._is_token_expired():
            return

        if not self._refresh_token:
            raise AuthenticationError(
                "Access token expired and no refresh token available. Please re-authenticate.",
                code="TOKEN_EXPIRED",
            )

        logger.info(
            "Auto-refreshing expired OAuth token",
            extra={'cif': self.company_cif}
        )

        try:
            oauth_service = get_oauth_service()
            new_tokens = oauth_service.refresh_access_token(
                self._refresh_token,
                self.company_cif,
            )

            # Update local state
            self._access_token = new_tokens.access_token
            self._refresh_token = new_tokens.refresh_token
            self._expires_at = new_tokens.expires_at

            # Persist to database
            from database import save_efactura_oauth_tokens
            save_efactura_oauth_tokens(self.company_cif, new_tokens.to_dict())

            # Reset session to use new token
            if self._session:
                self._session.close()
                self._session = None

            logger.info(
                "OAuth token refreshed successfully",
                extra={
                    'cif': self.company_cif,
                    'expires_at': self._expires_at.isoformat(),
                }
            )

        except ValueError as e:
            logger.error(
                "Failed to refresh OAuth token",
                extra={'cif': self.company_cif, 'error': str(e)}
            )
            raise AuthenticationError(
                f"Failed to refresh token: {e}. Please re-authenticate.",
                code="REFRESH_FAILED",
            ) from e

    def _get_session(self) -> requests.Session:
        """Get or create authenticated session with Bearer token."""
        self._refresh_token_if_needed()

        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        """Create requests session with OAuth Bearer token."""
        session = requests.Session()

        # Configure retries with exponential backoff
        retry_strategy = Retry(
            total=self.config.MAX_RETRIES,
            backoff_factor=self.config.RETRY_BASE_DELAY,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)

        # Set OAuth Bearer token in Authorization header
        session.headers.update({
            'Authorization': f'Bearer {self._access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'JARVIS-EFactura/1.0',
        })

        logger.info(
            "ANAF OAuth session created",
            extra={
                'environment': self.environment.value,
                'base_url': self.base_url,
                'cif': self.company_cif,
            }
        )

        return session

    def _hash_payload(self, data: Any) -> str:
        """Create hash of payload for logging (never log raw data)."""
        if data is None:
            return "null"
        content = str(data).encode()
        return hashlib.sha256(content).hexdigest()[:16]

    def _check_rate_limit(self):
        """Check and enforce rate limit."""
        max_requests = (
            self.config.MAX_REQUESTS_PER_MINUTE - self.config.RATE_LIMIT_BUFFER
        )

        if self._rate_limit.is_near_limit(max_requests, buffer=5):
            logger.warning(
                "Approaching rate limit",
                extra={
                    'requests_made': self._rate_limit.requests_made,
                    'remaining': self._rate_limit.get_remaining(
                        self.config.MAX_REQUESTS_PER_MINUTE
                    ),
                }
            )

        if self._rate_limit.get_remaining(max_requests) <= 0:
            raise RateLimitError(
                "Rate limit exceeded, please wait before making more requests",
                retry_after=60,  # 1 minute
            )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        expect_binary: bool = False,
    ) -> Dict[str, Any] | bytes:
        """
        Make HTTP request to ANAF API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data
            timeout: Request timeout in seconds
            expect_binary: If True, return raw bytes (for ZIP downloads)

        Returns:
            Parsed JSON response or raw bytes

        Raises:
            ANAFError: On any API error
        """
        self._check_rate_limit()

        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.config.REQUEST_TIMEOUT
        session = self._get_session()

        start_time = time.time()
        response = None

        try:
            logger.debug(
                "ANAF OAuth request",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'params_hash': self._hash_payload(params),
                    'data_hash': self._hash_payload(data),
                }
            )

            response = session.request(
                method=method,
                url=url,
                params=params,
                json=data if data else None,
                timeout=timeout,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            self._rate_limit.record_request()

            logger.info(
                "ANAF OAuth response",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'status_code': response.status_code,
                    'latency_ms': latency_ms,
                    'response_hash': self._hash_payload(
                        response.content[:1000] if response.content else None
                    ),
                }
            )

            # Handle different status codes
            if response.status_code == 401:
                # Token might be invalid/expired
                raise AuthenticationError(
                    "OAuth token rejected - please re-authenticate",
                    details={'status_code': 401},
                )

            if response.status_code == 403:
                raise AuthenticationError(
                    "Access forbidden - token may not be authorized for this CIF",
                    code="FORBIDDEN",
                    details={'status_code': 403},
                )

            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', 3600)
                raise RateLimitError(
                    "ANAF rate limit exceeded",
                    retry_after=int(retry_after),
                )

            if response.status_code == 404:
                raise InvoiceNotFoundError(
                    message_id=params.get('id', 'unknown') if params else 'unknown',
                )

            if response.status_code >= 400:
                error_body = response.text[:1000] if response.text else 'No response body'
                logger.error(
                    "ANAF API error response",
                    extra={
                        'status_code': response.status_code,
                        'url': url,
                        'params': params,
                        'response_body': error_body,
                    }
                )
                raise APIError(
                    message=f"ANAF API error: {response.status_code} - {error_body}",
                    status_code=response.status_code,
                    response_body=error_body,
                )

            if expect_binary:
                return response.content

            # Parse JSON response
            try:
                return response.json()
            except ValueError as e:
                raise ParseError(
                    f"Failed to parse JSON response: {e}",
                    content_type=response.headers.get('Content-Type'),
                )

        except requests.exceptions.Timeout as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "ANAF OAuth timeout",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'timeout_seconds': timeout,
                    'latency_ms': latency_ms,
                }
            )
            raise TimeoutError(
                f"Request timed out after {timeout}s",
                timeout_seconds=timeout,
            ) from e

        except requests.exceptions.ConnectionError as e:
            logger.error(
                "ANAF OAuth connection error",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'error': str(e),
                }
            )
            raise NetworkError(
                f"Connection failed: {e}",
                original_error=e,
            ) from e

        except requests.exceptions.RequestException as e:
            logger.error(
                "ANAF OAuth request error",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'error': str(e),
                }
            )
            raise NetworkError(
                f"Request failed: {e}",
                original_error=e,
            ) from e

    def list_messages(
        self,
        company_cif: Optional[str] = None,
        days: int = 60,
        page: int = 1,
        filter_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List messages (invoices) for the company using paginated endpoint.

        Args:
            company_cif: Ignored (uses self.company_cif for API compatibility)
            days: Number of days to look back
            page: Page number (1-based)
            filter_type: Optional filter - 'P' for received, 'T' for sent, None for all

        Returns:
            Dict with 'messages', 'has_more', 'next_page', pagination info
        """
        # Use instance's company_cif, ignore the parameter (for API compatibility)
        _ = company_cif  # Suppress unused warning
        cif = self.company_cif

        logger.info(
            "Listing messages (OAuth)",
            extra={
                'cif': cif,
                'days': days,
                'page': page,
                'filter_type': filter_type,
            }
        )

        # ANAF API requires startTime and endTime as Unix timestamps in milliseconds
        # (NOT the 'zile' parameter which is deprecated/not recognized)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        params = {
            'cif': self.company_cif,
            'startTime': int(start_time.timestamp() * 1000),  # Unix ms
            'endTime': int(end_time.timestamp() * 1000),      # Unix ms
            'pagina': page,
        }

        # Add filter only if specified (P=Primite/received, T=Trimise/sent, E=Both)
        if filter_type:
            params['filtru'] = filter_type

        response = self._make_request(
            'GET',
            '/listaMesajePaginatieFactura',
            params=params,
        )

        # Check for error response
        if 'eroare' in response:
            logger.error(
                "ANAF error listing messages",
                extra={'error': response['eroare'], 'cif': self.company_cif}
            )
            raise APIError(
                message=response['eroare'],
                status_code=400,
            )

        # Parse ANAF paginated response format
        messages = response.get('mesaje', [])
        total_pages = response.get('numar_total_pagini', 1)
        current_page = response.get('index_pagina_curenta', 1)
        total_records = response.get('numar_total_inregistrari', len(messages))
        records_per_page = response.get('numar_total_inregistrari_per_pagina', 100)

        has_more = current_page < total_pages
        next_page = current_page + 1 if has_more else None

        logger.info(
            "Messages listed (OAuth)",
            extra={
                'cif': self.company_cif,
                'message_count': len(messages),
                'has_more': has_more,
                'page': current_page,
                'total_pages': total_pages,
                'total_records': total_records,
            }
        )

        return {
            'messages': messages,
            'has_more': has_more,
            'next_page': next_page,
            'current_page': current_page,
            'total_pages': total_pages,
            'total_records': total_records,
            'records_per_page': records_per_page,
            'serial': response.get('serial'),
            'title': response.get('titlu'),
        }

    def download_message(self, download_id: str) -> bytes:
        """
        Download invoice ZIP file from ANAF.

        Args:
            download_id: ANAF download ID (from message 'id' field)

        Returns:
            ZIP file content as bytes (contains XML + signature)
        """
        logger.info(
            "Downloading invoice (OAuth)",
            extra={'download_id': download_id}
        )

        content = self._make_request(
            'GET',
            '/descarcare',
            params={'id': download_id},
            timeout=self.config.DOWNLOAD_TIMEOUT,
            expect_binary=True,
        )

        logger.info(
            "Invoice downloaded (OAuth)",
            extra={
                'download_id': download_id,
                'size_bytes': len(content),
            }
        )

        return content

    def xml_to_pdf(
        self,
        xml_content: str,
        standard: str = 'FACT1',
        validate: bool = True,
    ) -> bytes:
        """
        Convert e-Factura XML to PDF using ANAF's official conversion API.

        Args:
            xml_content: The invoice XML content as string
            standard: 'FACT1' for regular invoices, 'FCN' for credit notes
            validate: Whether to validate XML before conversion

        Returns:
            PDF file content as bytes
        """
        if standard not in ('FACT1', 'FCN'):
            raise ValueError(f"Invalid standard: {standard}. Must be 'FACT1' or 'FCN'")

        validate_path = '/DA' if validate else ''
        endpoint = f'/transformare/{standard}{validate_path}'

        logger.info(
            "Converting XML to PDF (OAuth)",
            extra={'standard': standard, 'validate': validate}
        )

        # For XML to PDF, we need to send raw XML
        session = self._get_session()
        url = f"{self.base_url}{endpoint}"

        response = session.post(
            url,
            data=xml_content.encode('utf-8'),
            headers={
                **session.headers,
                'Content-Type': 'text/plain',
            },
            timeout=self.config.DOWNLOAD_TIMEOUT,
        )

        if response.status_code >= 400:
            raise APIError(
                message=f"PDF conversion failed: {response.status_code}",
                status_code=response.status_code,
                response_body=response.text[:500] if response.text else None,
            )

        logger.info(
            "XML converted to PDF (OAuth)",
            extra={'pdf_size_bytes': len(response.content)}
        )

        return response.content

    def get_token_info(self) -> Dict[str, Any]:
        """Get information about current OAuth token."""
        return {
            'cif': self.company_cif,
            'has_access_token': bool(self._access_token),
            'has_refresh_token': bool(self._refresh_token),
            'expires_at': self._expires_at.isoformat() if self._expires_at else None,
            'is_expired': self._is_token_expired(),
        }

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        return {
            'requests_made': self._rate_limit.requests_made,
            'max_per_minute': self.config.MAX_REQUESTS_PER_MINUTE,
            'remaining': self._rate_limit.get_remaining(
                self.config.MAX_REQUESTS_PER_MINUTE
            ),
            'window_start': self._rate_limit.window_start.isoformat(),
            'is_near_limit': self._rate_limit.is_near_limit(
                self.config.MAX_REQUESTS_PER_MINUTE,
                self.config.RATE_LIMIT_BUFFER,
            ),
        }

    def close(self):
        """Close the client session."""
        if self._session:
            self._session.close()
            self._session = None
            logger.debug("ANAF OAuth session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()
        return False


def get_anaf_client_for_cif(
    company_cif: str,
    environment: Environment = Environment.PRODUCTION,
) -> ANAFOAuthClient:
    """
    Get an ANAF client for a company, using stored OAuth tokens.

    This is the recommended way to get a client for API calls.

    Args:
        company_cif: Company CIF
        environment: API environment

    Returns:
        ANAFOAuthClient instance configured with stored tokens

    Raises:
        AuthenticationError: If no valid tokens found
    """
    return ANAFOAuthClient.from_stored_tokens(
        company_cif=company_cif,
        environment=environment,
    )
