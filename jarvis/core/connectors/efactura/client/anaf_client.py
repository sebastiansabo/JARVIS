"""
ANAF e-Factura API Client

HTTP client for ANAF's e-Factura REST API with certificate-based authentication.
Handles rate limiting, retries, and structured logging.

This is a core connector - available across all JARVIS sections.
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
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

logger = get_logger('jarvis.core.connectors.efactura.client')


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


class ANAFClient:
    """
    Client for ANAF e-Factura REST API.

    Uses X.509 certificate-based mutual TLS authentication.
    Implements retry logic, rate limiting, and structured logging.
    """

    def __init__(
        self,
        cert_path: str,
        cert_password: str,
        environment: Environment = Environment.TEST,
        config: Optional[ANAFConfig] = None,
    ):
        """
        Initialize ANAF client.

        Args:
            cert_path: Path to .p12/.pfx certificate file
            cert_password: Password to decrypt the certificate
            environment: API environment (test or production)
            config: Optional custom configuration
        """
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.environment = environment
        self.config = config or DEFAULT_CONFIG

        self.base_url = self.config.get_base_url(environment)
        self._session: Optional[requests.Session] = None
        self._rate_limit = RateLimitState()

        # Certificate state
        self._cert_loaded = False
        self._cert_expires_at: Optional[datetime] = None

    def _get_session(self) -> requests.Session:
        """Get or create authenticated session with retry logic."""
        if self._session is None:
            self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        """Create requests session with certificate and retry config."""
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

        # Configure certificate authentication
        session.cert = self._load_cert_for_requests()

        # Set default headers
        session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'JARVIS-EFactura/1.0',
        })

        self._cert_loaded = True
        logger.info(
            "ANAF session created",
            extra={
                'environment': self.environment.value,
                'base_url': self.base_url,
            }
        )

        return session

    def _load_cert_for_requests(self) -> Tuple[str, str]:
        """
        Load certificate for requests library.

        Returns tuple of (cert_path, key_path) for PEM files.
        """
        from ..services.auth_service import CertificateAuthService

        auth_service = CertificateAuthService()
        return auth_service.get_cert_files_for_requests(
            self.cert_path,
            self.cert_password
        )

    def _hash_payload(self, data: Any) -> str:
        """Create hash of payload for logging (never log raw data)."""
        if data is None:
            return "null"
        content = str(data).encode()
        return hashlib.sha256(content).hexdigest()[:16]

    def _check_rate_limit(self):
        """Check and enforce rate limit."""
        max_requests = (
            self.config.MAX_REQUESTS_PER_HOUR - self.config.RATE_LIMIT_BUFFER
        )

        if self._rate_limit.is_near_limit(max_requests, buffer=5):
            logger.warning(
                "Approaching rate limit",
                extra={
                    'requests_made': self._rate_limit.requests_made,
                    'remaining': self._rate_limit.get_remaining(
                        self.config.MAX_REQUESTS_PER_HOUR
                    ),
                }
            )

        if self._rate_limit.get_remaining(max_requests) <= 0:
            raise RateLimitError(
                "Rate limit exceeded, please wait before making more requests",
                retry_after=3600,  # 1 hour
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
                "ANAF request",
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
                "ANAF response",
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
                raise AuthenticationError(
                    "Authentication failed - check certificate",
                    details={'status_code': 401},
                )

            if response.status_code == 403:
                raise AuthenticationError(
                    "Access forbidden - certificate may not be authorized for this CIF",
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
                raise APIError(
                    message=f"ANAF API error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text[:500] if response.text else None,
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
                "ANAF timeout",
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

        except requests.exceptions.SSLError as e:
            logger.error(
                "ANAF SSL error",
                extra={
                    'method': method,
                    'endpoint': endpoint,
                    'error': str(e),
                }
            )
            raise AuthenticationError(
                f"SSL/TLS error - check certificate: {e}",
                code="SSL_ERROR",
            ) from e

        except requests.exceptions.ConnectionError as e:
            logger.error(
                "ANAF connection error",
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
                "ANAF request error",
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

    def authenticate(self) -> bool:
        """
        Verify certificate authentication works.

        Returns:
            True if authentication is successful

        Raises:
            AuthenticationError: If authentication fails
        """
        logger.info("Verifying ANAF authentication")

        try:
            self._make_request('GET', '/status')
            logger.info("ANAF authentication verified")
            return True
        except ANAFError:
            raise
        except Exception as e:
            raise AuthenticationError(
                f"Authentication verification failed: {e}"
            ) from e

    def list_messages(
        self,
        company_cif: str,
        days: int = 60,
        page: int = 1,
        filter_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List messages (invoices) for a company using paginated endpoint.

        Args:
            company_cif: Company CIF (without RO prefix)
            days: Number of days to look back
            page: Page number (1-based)
            filter_type: Optional filter - 'P' for received, 'T' for sent, None for all

        Returns:
            Dict with 'messages', 'has_more', 'next_page', pagination info
        """
        logger.info(
            "Listing messages",
            extra={
                'cif': company_cif,
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
            'cif': company_cif,
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
                extra={'error': response['eroare'], 'cif': company_cif}
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
            "Messages listed",
            extra={
                'cif': company_cif,
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

    def list_received_messages(
        self,
        company_cif: str,
        days: int = 60,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        List received invoices (facturile primite).

        Args:
            company_cif: Company CIF (without RO prefix)
            days: Number of days to look back
            page: Page number (1-based)

        Returns:
            Dict with 'messages', 'has_more', pagination info
        """
        return self.list_messages(
            company_cif=company_cif,
            days=days,
            page=page,
            filter_type='P',  # Primite = received
        )

    def list_sent_messages(
        self,
        company_cif: str,
        days: int = 60,
        page: int = 1,
    ) -> Dict[str, Any]:
        """
        List sent invoices (facturile trimise).

        Args:
            company_cif: Company CIF (without RO prefix)
            days: Number of days to look back
            page: Page number (1-based)

        Returns:
            Dict with 'messages', 'has_more', pagination info
        """
        return self.list_messages(
            company_cif=company_cif,
            days=days,
            page=page,
            filter_type='T',  # Trimise = sent
        )

    def download_message(
        self,
        download_id: str,
    ) -> bytes:
        """
        Download invoice ZIP file from ANAF.

        Args:
            download_id: ANAF download ID (from message 'id' field)

        Returns:
            ZIP file content as bytes (contains XML + signature)
        """
        logger.info(
            "Downloading invoice",
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
            "Invoice downloaded",
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

        Raises:
            ValueError: If standard is not 'FACT1' or 'FCN'
            APIError: If conversion fails
        """
        if standard not in ('FACT1', 'FCN'):
            raise ValueError(f"Invalid standard: {standard}. Must be 'FACT1' or 'FCN'")

        validate_path = '/DA' if validate else ''
        endpoint = f'/transformare/{standard}{validate_path}'

        logger.info(
            "Converting XML to PDF",
            extra={'standard': standard, 'validate': validate}
        )

        pdf_content = self._make_request(
            'POST',
            endpoint,
            data=xml_content.encode('utf-8'),
            headers={'Content-Type': 'text/plain'},
            timeout=self.config.DOWNLOAD_TIMEOUT,
            expect_binary=True,
        )

        logger.info(
            "XML converted to PDF",
            extra={'pdf_size_bytes': len(pdf_content)}
        )

        return pdf_content

    def list_all_messages(
        self,
        company_cif: str,
        days: int = 60,
    ) -> Dict[str, Any]:
        """
        List all messages (both received and sent) without filtering.

        Args:
            company_cif: Company CIF (without RO prefix)
            days: Number of days to look back

        Returns:
            Dict with 'messages', 'has_more', pagination info
        """
        return self.list_messages(
            company_cif=company_cif,
            days=days,
            page=1,
            filter_type=None,  # No filter = all messages
        )

    def fetch_all_pages(
        self,
        company_cif: str,
        days: int = 60,
        filter_type: Optional[str] = None,
        max_pages: int = 100,
    ) -> list:
        """
        Fetch all messages across all pages.

        Args:
            company_cif: Company CIF
            days: Days to look back
            filter_type: 'P' for received, 'T' for sent, None for all
            max_pages: Safety limit for max pages to fetch

        Returns:
            List of all messages
        """
        all_messages = []
        page = 1

        while page <= max_pages:
            result = self.list_messages(
                company_cif=company_cif,
                days=days,
                page=page,
                filter_type=filter_type,
            )

            all_messages.extend(result['messages'])

            if not result['has_more']:
                break

            page += 1

        logger.info(
            "Fetched all pages",
            extra={
                'cif': company_cif,
                'total_messages': len(all_messages),
                'pages_fetched': page,
            }
        )

        return all_messages

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        return {
            'requests_made': self._rate_limit.requests_made,
            'max_per_hour': self.config.MAX_REQUESTS_PER_HOUR,
            'remaining': self._rate_limit.get_remaining(
                self.config.MAX_REQUESTS_PER_HOUR
            ),
            'window_start': self._rate_limit.window_start.isoformat(),
            'is_near_limit': self._rate_limit.is_near_limit(
                self.config.MAX_REQUESTS_PER_HOUR,
                self.config.RATE_LIMIT_BUFFER,
            ),
        }

    def close(self):
        """Close the client session."""
        if self._session:
            self._session.close()
            self._session = None
            logger.debug("ANAF session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()
        return False
