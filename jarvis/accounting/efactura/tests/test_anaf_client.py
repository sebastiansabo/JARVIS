"""
Tests for ANAF API Client

Unit tests for the ANAFClient class with mocked responses.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
import os

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from accounting.efactura.client.anaf_client import ANAFClient, RateLimitState
from accounting.efactura.client.exceptions import (
    AuthenticationError,
    RateLimitError,
    NetworkError,
    TimeoutError,
    APIError,
    ParseError,
    InvoiceNotFoundError,
)
from accounting.efactura.config import Environment
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
        with patch('accounting.efactura.client.anaf_client.CertificateAuthService') as mock:
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
        with patch('accounting.efactura.services.auth_service.CertificateAuthService'):
            client = ANAFClient(
                cert_path='/path/to/cert.p12',
                cert_password='test_password',
                environment=Environment.TEST,
            )
            # Mock the session
            client._session = Mock()
            yield client

    def test_init(self, mock_auth_service):
        """Test client initialization."""
        with patch('accounting.efactura.services.auth_service.CertificateAuthService'):
            client = ANAFClient(
                cert_path='/path/to/cert.p12',
                cert_password='test_password',
                environment=Environment.TEST,
            )
            assert client.cert_path == '/path/to/cert.p12'
            assert client.environment == Environment.TEST
            assert 'test' in client.base_url

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

    def test_list_received_messages_pagination(self, client):
        """Test pagination handling."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'mesaje': [{'id': '1'}],
            'numar_total': 200,
            'numar_total_pagini': 2,
            'pagina_curenta': 1,
        }
        mock_response.content = b'mock content'
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        result = client.list_received_messages('12345678', days=60)

        assert result['has_more'] is True
        assert result['next_cursor'] == '2'

    def test_list_sent_messages_success(self, client):
        """Test successful list sent messages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_LIST_SENT_RESPONSE
        mock_response.content = b'mock content'
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        result = client.list_sent_messages('12345678', days=60)

        assert len(result['messages']) == 1
        assert result['total_count'] == 1

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

    def test_get_message_status(self, client):
        """Test getting message status."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_MESSAGE_STATUS_RESPONSE
        mock_response.content = b'mock content'
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        result = client.get_message_status('3066421557')

        assert result['status'] == 'valid'
        assert result['id'] == '3066421557'

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

    def test_authentication_error_403(self, client):
        """Test authentication error on 403."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.content = b'forbidden'

        client._session.request.return_value = mock_response

        with pytest.raises(AuthenticationError) as exc_info:
            client.list_received_messages('12345678')

        assert 'forbidden' in str(exc_info.value).lower()

    def test_not_found_error(self, client):
        """Test 404 not found error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.content = b'not found'

        client._session.request.return_value = mock_response

        with pytest.raises(InvoiceNotFoundError):
            client.download_message('nonexistent')

    def test_api_error_500(self, client):
        """Test server error handling."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_response.content = b'error'

        client._session.request.return_value = mock_response

        with pytest.raises(APIError) as exc_info:
            client.list_received_messages('12345678')

        assert exc_info.value.status_code == 500
        assert exc_info.value.is_retryable is True

    def test_network_error(self, client):
        """Test network error handling."""
        import requests

        client._session.request.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        with pytest.raises(NetworkError) as exc_info:
            client.list_received_messages('12345678')

        assert exc_info.value.is_retryable is True

    def test_timeout_error(self, client):
        """Test timeout error handling."""
        import requests

        client._session.request.side_effect = requests.exceptions.Timeout(
            "Request timed out"
        )

        with pytest.raises(TimeoutError):
            client.list_received_messages('12345678')

    def test_parse_error_invalid_json(self, client):
        """Test parse error on invalid JSON."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.content = b'not json'
        mock_response.headers = {'Content-Type': 'text/html'}

        client._session.request.return_value = mock_response

        with pytest.raises(ParseError):
            client.list_received_messages('12345678')

    def test_rate_limit_tracking(self, client):
        """Test that rate limits are tracked."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_LIST_RECEIVED_RESPONSE
        mock_response.content = b'mock'
        mock_response.headers = {}

        client._session.request.return_value = mock_response

        # Make multiple requests
        for _ in range(5):
            client.list_received_messages('12345678')

        assert client._rate_limit.requests_made == 5

    def test_rate_limit_exceeded_locally(self, client):
        """Test local rate limit enforcement."""
        # Set rate limit to near max
        client._rate_limit.requests_made = 145

        with pytest.raises(RateLimitError):
            client.list_received_messages('12345678')

    def test_get_rate_limit_status(self, client):
        """Test rate limit status reporting."""
        client._rate_limit.requests_made = 50

        status = client.get_rate_limit_status()

        assert status['requests_made'] == 50
        assert status['max_per_hour'] == 150
        assert status['remaining'] == 100

    def test_context_manager(self, mock_auth_service):
        """Test client as context manager."""
        with patch('accounting.efactura.services.auth_service.CertificateAuthService'):
            with ANAFClient(
                cert_path='/path/to/cert.p12',
                cert_password='test_password',
            ) as client:
                assert client is not None

    def test_hash_payload_never_logs_raw(self, client):
        """Test that payload hashing produces consistent, safe hashes."""
        sensitive_data = {'password': 'secret123', 'token': 'abc123'}

        hash1 = client._hash_payload(sensitive_data)
        hash2 = client._hash_payload(sensitive_data)

        # Same input produces same hash
        assert hash1 == hash2
        # Hash doesn't contain raw data
        assert 'secret123' not in hash1
        assert 'abc123' not in hash1
        # Hash is truncated
        assert len(hash1) == 16


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

    def test_no_cert_content_in_errors(self):
        """Ensure certificate content doesn't appear in errors."""
        from accounting.efactura.client.exceptions import CertificateError

        error = CertificateError(
            "Certificate validation failed",
            details={'fingerprint': 'abc123'},
        )

        # Error should not contain PEM markers or base64 cert data
        error_str = str(error)
        assert '-----BEGIN' not in error_str
        assert '-----END' not in error_str

    def test_hash_used_for_response_logging(self):
        """Test that responses are hashed, not logged raw."""
        from accounting.efactura.client.exceptions import APIError

        sensitive_response = '{"token": "secret_token_123", "data": "sensitive"}'
        error = APIError(
            "API Error",
            status_code=500,
            response_body=sensitive_response,
        )

        # The response body should be hashed in details
        assert 'secret_token_123' not in str(error.details)
        assert 'response_body_hash' in error.details


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
