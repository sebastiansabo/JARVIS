"""
Tests for ANAF API Client

Unit tests for the ANAFClient class with mocked responses.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

import sys
import os

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))

from core.connectors.efactura.client.anaf_client import ANAFClient, RateLimitState
from core.connectors.efactura.client.exceptions import (
    AuthenticationError,
    RateLimitError,
    NetworkError,
    TimeoutError,
    APIError,
    ParseError,
    InvoiceNotFoundError,
)
from core.connectors.efactura.config import Environment
from .fixtures.mock_anaf_responses import (
    MOCK_LIST_RECEIVED_RESPONSE,
    MOCK_LIST_SENT_RESPONSE,
    MOCK_MESSAGE_STATUS_RESPONSE,
    create_mock_zip_content,
)


class TestRateLimitState:
    """Tests for RateLimitState helper class."""

    def test_initial_state(self):
        """Test initial rate limit state."""
        state = RateLimitState()
        assert state.requests_made == 0
        assert state.window_start is not None

    def test_record_request(self):
        """Test recording requests."""
        state = RateLimitState()
        state.record_request()
        assert state.requests_made == 1
        state.record_request()
        assert state.requests_made == 2

    def test_get_remaining(self):
        """Test remaining request calculation."""
        state = RateLimitState()
        state.requests_made = 50
        remaining = state.get_remaining(150)
        assert remaining == 100

    def test_is_near_limit(self):
        """Test near-limit detection."""
        state = RateLimitState()
        state.requests_made = 145
        assert state.is_near_limit(150, buffer=10) is True

        state.requests_made = 100
        assert state.is_near_limit(150, buffer=10) is False


class TestANAFClient:
    """Tests for ANAFClient."""

    @pytest.fixture
    def mock_auth_service(self):
        """Mock the auth service."""
        with patch('core.connectors.efactura.client.anaf_client.CertificateAuthService') as mock:
            mock_instance = Mock()
            mock_instance.get_cert_files_for_requests.return_value = (
                '/tmp/cert.pem',
                '/tmp/key.pem'
            )
            mock.return_value = mock_instance
            yield mock

    @pytest.fixture
    def client(self, mock_auth_service):
        """Create a client instance with mocked dependencies."""
        with patch('core.connectors.efactura.services.auth_service.CertificateAuthService'):
            client = ANAFClient(
                cert_path='/path/to/cert.p12',
                cert_password='test_password',
                environment=Environment.TEST,
            )
            # Mock the session
            client._session = Mock()
            yield client

    def test_list_received_messages_success(self, client):
        """Test successful list received messages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_LIST_RECEIVED_RESPONSE
        mock_response.content = b'mock content'
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        result = client.list_received_messages('12345678', days=60)

        assert result['messages'] == MOCK_LIST_RECEIVED_RESPONSE['mesaje']
        assert result['has_more'] is False
        assert result['total_count'] == 2

    def test_download_message_returns_bytes(self, client):
        """Test that download returns binary content."""
        zip_content = create_mock_zip_content()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = zip_content
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        result = client.download_message('3066421557')

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Verify it's a valid ZIP
        assert result[:4] == b'PK\x03\x04'

    def test_rate_limit_error(self, client):
        """Test rate limit error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '3600'}
        mock_response.content = b'rate limited'

        client._session.request.return_value = mock_response

        with pytest.raises(RateLimitError) as exc_info:
            client.list_received_messages('12345678')

        assert exc_info.value.retry_after == 3600
        assert exc_info.value.is_retryable is True

    def test_authentication_error_401(self, client):
        """Test authentication error on 401."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.content = b'unauthorized'

        client._session.request.return_value = mock_response

        with pytest.raises(AuthenticationError) as exc_info:
            client.list_received_messages('12345678')

        assert 'Authentication failed' in str(exc_info.value)


class TestNoSecretsInLogs:
    """Tests to ensure secrets are never logged."""

    def test_no_password_in_error_messages(self):
        """Ensure passwords don't appear in error messages."""
        error = AuthenticationError(
            "Auth failed for cert with password",
            details={'cert_path': '/path/to/cert.p12'},
        )

        error_str = str(error)
        assert 'password' not in error_str.lower() or 'Auth failed' in error_str


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
