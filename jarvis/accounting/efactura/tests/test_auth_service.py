"""
Tests for Certificate Authentication Service

Unit tests for certificate loading, validation, and TLS session management.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import tempfile
import os

import sys

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from accounting.efactura.services.auth_service import (
    CertificateAuthService,
    CertificateInfo,
)
from accounting.efactura.client.exceptions import (
    CertificateError,
    CertificateExpiredError,
)


class TestCertificateInfo:
    """Tests for CertificateInfo dataclass."""

    def test_cert_info_creation(self):
        """Test creating certificate info."""
        info = CertificateInfo(
            subject='CN=Test',
            issuer='CN=TestCA',
            serial_number='123abc',
            not_before=datetime(2024, 1, 1),
            not_after=datetime(2025, 12, 31),
            fingerprint_sha256='abc123...',
        )

        assert info.subject == 'CN=Test'
        assert info.serial_number == '123abc'


class TestCertificateAuthService:
    """Tests for CertificateAuthService."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return CertificateAuthService()

    def test_init(self, service):
        """Test service initialization."""
        assert service.config is not None
        assert service._temp_files == []

    @patch('accounting.efactura.services.auth_service.pkcs12')
    @patch('builtins.open', create=True)
    def test_load_certificate_file_not_found(self, mock_open, mock_pkcs12, service):
        """Test error when certificate file not found."""
        mock_open.side_effect = FileNotFoundError()

        with pytest.raises(CertificateError) as exc_info:
            service.load_certificate('/nonexistent/cert.p12', 'password')

        assert 'not found' in str(exc_info.value)

    @patch('accounting.efactura.services.auth_service.pkcs12')
    @patch('builtins.open', create=True)
    def test_load_certificate_permission_denied(self, mock_open, mock_pkcs12, service):
        """Test error when permission denied."""
        mock_open.side_effect = PermissionError()

        with pytest.raises(CertificateError) as exc_info:
            service.load_certificate('/protected/cert.p12', 'password')

        assert 'Permission denied' in str(exc_info.value)

    @patch('accounting.efactura.services.auth_service.pkcs12')
    def test_load_certificate_wrong_password(self, mock_pkcs12, service):
        """Test error with wrong password."""
        mock_pkcs12.load_key_and_certificates.side_effect = ValueError(
            "Bad password"
        )

        with pytest.raises(CertificateError) as exc_info:
            service.load_certificate_from_bytes(b'cert_data', 'wrong_password')

        assert 'password' in str(exc_info.value).lower()

    @patch('accounting.efactura.services.auth_service.pkcs12')
    def test_load_certificate_no_cert_in_file(self, mock_pkcs12, service):
        """Test error when no certificate in file."""
        mock_pkcs12.load_key_and_certificates.return_value = (
            Mock(),  # private key
            None,    # no certificate
            [],
        )

        with pytest.raises(CertificateError) as exc_info:
            service.load_certificate_from_bytes(b'cert_data', 'password')

        assert 'No certificate found' in str(exc_info.value)

    @patch('accounting.efactura.services.auth_service.pkcs12')
    def test_load_certificate_no_key_in_file(self, mock_pkcs12, service):
        """Test error when no private key in file."""
        mock_cert = Mock()
        mock_pkcs12.load_key_and_certificates.return_value = (
            None,       # no private key
            mock_cert,  # certificate
            [],
        )

        with pytest.raises(CertificateError) as exc_info:
            service.load_certificate_from_bytes(b'cert_data', 'password')

        assert 'No private key found' in str(exc_info.value)

    @patch('accounting.efactura.services.auth_service.pkcs12')
    def test_load_certificate_expired(self, mock_pkcs12, service):
        """Test error when certificate is expired."""
        # Create mock certificate that's expired
        mock_cert = Mock()
        mock_cert.not_valid_before_utc = datetime(2020, 1, 1)
        mock_cert.not_valid_after_utc = datetime(2020, 12, 31)  # Expired
        mock_cert.subject = []
        mock_cert.issuer = Mock()
        mock_cert.issuer.rfc4514_string.return_value = 'CN=TestCA'
        mock_cert.serial_number = 123
        mock_cert.public_bytes.return_value = b'cert_bytes'

        mock_key = Mock()

        mock_pkcs12.load_key_and_certificates.return_value = (
            mock_key,
            mock_cert,
            [],
        )

        with pytest.raises(CertificateExpiredError):
            service.load_certificate_from_bytes(b'cert_data', 'password')

    def test_validate_cert_expiry_valid(self, service):
        """Test validating a valid certificate."""
        mock_cert = Mock()
        mock_cert.not_valid_after_utc = datetime.utcnow() + timedelta(days=100)

        is_valid, days = service.validate_cert_expiry(mock_cert)

        assert is_valid is True
        assert days >= 99  # Allow for test execution time

    def test_validate_cert_expiry_expired(self, service):
        """Test validating an expired certificate."""
        mock_cert = Mock()
        mock_cert.not_valid_after_utc = datetime.utcnow() - timedelta(days=1)

        is_valid, days = service.validate_cert_expiry(mock_cert)

        assert is_valid is False
        assert days == 0

    def test_validate_cert_expiry_expiring_soon(self, service):
        """Test detecting certificate expiring soon."""
        mock_cert = Mock()
        mock_cert.not_valid_after_utc = datetime.utcnow() + timedelta(days=15)

        is_valid, days = service.validate_cert_expiry(mock_cert)

        assert is_valid is True
        assert days < 30  # Should trigger warning

    @patch('accounting.efactura.services.auth_service.pkcs12')
    def test_store_certificate_metadata(self, mock_pkcs12, service):
        """Test storing certificate returns proper metadata."""
        # Create valid mock certificate
        mock_cert = Mock()
        mock_cert.not_valid_before_utc = datetime(2024, 1, 1)
        mock_cert.not_valid_after_utc = datetime(2025, 12, 31)
        mock_cert.subject = []
        mock_cert.issuer = Mock()
        mock_cert.issuer.rfc4514_string.return_value = 'CN=TestCA'
        mock_cert.serial_number = 123
        mock_cert.public_bytes.return_value = b'cert_bytes'

        mock_key = Mock()

        mock_pkcs12.load_key_and_certificates.return_value = (
            mock_key,
            mock_cert,
            [],
        )

        result = service.store_certificate(
            company_cif='12345678',
            cert_data=b'cert_data',
            password='password',
        )

        assert result['cif'] == '12345678'
        assert 'cert_hash' in result
        assert 'fingerprint' in result
        assert result['is_valid'] is True

    def test_cleanup_removes_temp_files(self, service):
        """Test cleanup removes temporary files."""
        # Create temp files
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, 'test.txt')
        with open(temp_file, 'w') as f:
            f.write('test')

        service._temp_files = [temp_file, temp_dir]

        service.cleanup()

        assert not os.path.exists(temp_file)
        assert not os.path.exists(temp_dir)
        assert service._temp_files == []


class TestCertificateInvalidCert:
    """Tests for invalid certificate scenarios."""

    @pytest.fixture
    def service(self):
        return CertificateAuthService()

    def test_certificate_not_yet_valid(self, service):
        """Test error when certificate is not yet valid."""
        # Create a CertificateInfo that's not yet valid
        info = CertificateInfo(
            subject='CN=Test',
            issuer='CN=TestCA',
            serial_number='123',
            not_before=datetime.utcnow() + timedelta(days=30),  # Future
            not_after=datetime.utcnow() + timedelta(days=365),
            fingerprint_sha256='abc123',
        )

        with pytest.raises(CertificateError) as exc_info:
            service._validate_expiry(info)

        assert 'not yet valid' in str(exc_info.value)

    def test_certificate_expired_error_contains_date(self, service):
        """Test that expired error includes expiry date."""
        info = CertificateInfo(
            subject='CN=Test',
            issuer='CN=TestCA',
            serial_number='123',
            not_before=datetime(2020, 1, 1),
            not_after=datetime(2020, 6, 1),  # Expired
            fingerprint_sha256='abc123',
        )

        with pytest.raises(CertificateExpiredError) as exc_info:
            service._validate_expiry(info)

        assert '2020-06-01' in str(exc_info.value)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
