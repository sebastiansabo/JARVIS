"""
Certificate Authentication Service

Handles X.509 certificate loading, validation, and TLS session management
for ANAF e-Factura API authentication.
"""

import os
import tempfile
import hashlib
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend

from core.utils.logging_config import get_logger
from ..client.exceptions import (
    CertificateError,
    CertificateExpiredError,
    CertificateExpiringError,
)
from ..config import DEFAULT_CONFIG

logger = get_logger('jarvis.accounting.efactura.auth')


@dataclass
class CertificateInfo:
    """Information extracted from a certificate."""
    subject: str
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    organization: Optional[str] = None
    common_name: Optional[str] = None


class CertificateAuthService:
    """
    Service for X.509 certificate authentication.

    Handles loading PKCS12 (.p12/.pfx) certificates, validating expiry,
    and preparing credentials for TLS mutual authentication.
    """

    def __init__(self, config=None):
        """Initialize the auth service."""
        self.config = config or DEFAULT_CONFIG
        self._temp_files: list = []  # Track temp files for cleanup

    def load_certificate(
        self,
        cert_path: str,
        password: str,
    ) -> Tuple[x509.Certificate, Any, CertificateInfo]:
        """
        Load and parse a PKCS12 certificate.

        Args:
            cert_path: Path to .p12/.pfx file
            password: Password to decrypt the certificate

        Returns:
            Tuple of (certificate, private_key, certificate_info)

        Raises:
            CertificateError: If loading fails
            CertificateExpiredError: If certificate has expired
        """
        logger.info(
            "Loading certificate",
            extra={'cert_path_hash': hashlib.sha256(cert_path.encode()).hexdigest()[:8]}
        )

        try:
            with open(cert_path, 'rb') as f:
                cert_data = f.read()
        except FileNotFoundError:
            raise CertificateError(f"Certificate file not found: {cert_path}")
        except PermissionError:
            raise CertificateError(f"Permission denied reading certificate: {cert_path}")
        except IOError as e:
            raise CertificateError(f"Error reading certificate file: {e}")

        return self.load_certificate_from_bytes(cert_data, password)

    def load_certificate_from_bytes(
        self,
        cert_data: bytes,
        password: str,
    ) -> Tuple[x509.Certificate, Any, CertificateInfo]:
        """
        Load certificate from bytes (for vault-stored certs).

        Args:
            cert_data: PKCS12 certificate as bytes
            password: Password to decrypt

        Returns:
            Tuple of (certificate, private_key, certificate_info)
        """
        try:
            # Load PKCS12 certificate
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                cert_data,
                password.encode() if password else None,
                default_backend()
            )

            if certificate is None:
                raise CertificateError("No certificate found in PKCS12 file")

            if private_key is None:
                raise CertificateError("No private key found in PKCS12 file")

            # Extract certificate info
            cert_info = self._extract_cert_info(certificate)

            # Validate expiry
            self._validate_expiry(cert_info)

            logger.info(
                "Certificate loaded successfully",
                extra={
                    'subject': cert_info.subject,
                    'expires': cert_info.not_after.isoformat(),
                    'fingerprint': cert_info.fingerprint_sha256[:16],
                }
            )

            return certificate, private_key, cert_info

        except ValueError as e:
            # Wrong password or invalid format
            if "password" in str(e).lower():
                raise CertificateError(
                    "Invalid certificate password",
                    code="WRONG_PASSWORD",
                )
            raise CertificateError(f"Invalid certificate format: {e}")
        except Exception as e:
            raise CertificateError(f"Failed to load certificate: {e}")

    def _extract_cert_info(self, cert: x509.Certificate) -> CertificateInfo:
        """Extract information from X.509 certificate."""
        # Get subject components
        subject_parts = []
        org = None
        cn = None

        for attr in cert.subject:
            subject_parts.append(f"{attr.oid._name}={attr.value}")
            if attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                org = attr.value
            elif attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value

        # Calculate fingerprint
        fingerprint = hashlib.sha256(
            cert.public_bytes(serialization.Encoding.DER)
        ).hexdigest()

        return CertificateInfo(
            subject=', '.join(subject_parts),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=format(cert.serial_number, 'x'),
            not_before=cert.not_valid_before_utc.replace(tzinfo=None),
            not_after=cert.not_valid_after_utc.replace(tzinfo=None),
            fingerprint_sha256=fingerprint,
            organization=org,
            common_name=cn,
        )

    def _validate_expiry(self, cert_info: CertificateInfo):
        """
        Validate certificate expiry.

        Raises:
            CertificateExpiredError: If certificate has expired
            CertificateExpiringError: If expiring soon (as warning, logged)
        """
        now = datetime.utcnow()

        if now < cert_info.not_before:
            raise CertificateError(
                f"Certificate not yet valid (valid from {cert_info.not_before})",
                code="NOT_YET_VALID",
            )

        if now > cert_info.not_after:
            raise CertificateExpiredError(
                expires_at=cert_info.not_after.isoformat(),
            )

        days_remaining = (cert_info.not_after - now).days

        if days_remaining < self.config.CERT_EXPIRY_WARNING_DAYS:
            logger.warning(
                "Certificate expiring soon",
                extra={
                    'days_remaining': days_remaining,
                    'expires_at': cert_info.not_after.isoformat(),
                }
            )
            # Don't raise - just warn

    def validate_cert_expiry(
        self,
        cert: x509.Certificate,
    ) -> Tuple[bool, int]:
        """
        Check if certificate is valid and days until expiry.

        Args:
            cert: X.509 certificate object

        Returns:
            Tuple of (is_valid, days_until_expiry)
        """
        now = datetime.utcnow()
        not_after = cert.not_valid_after_utc.replace(tzinfo=None)

        is_valid = now < not_after
        days_remaining = (not_after - now).days if is_valid else 0

        return is_valid, days_remaining

    def get_cert_files_for_requests(
        self,
        cert_path: str,
        password: str,
    ) -> Tuple[str, str]:
        """
        Prepare certificate files for requests library.

        The requests library needs separate PEM files for cert and key.
        This method extracts them from PKCS12 and writes to temp files.

        Args:
            cert_path: Path to PKCS12 certificate
            password: Certificate password

        Returns:
            Tuple of (cert_pem_path, key_pem_path)
        """
        cert, private_key, cert_info = self.load_certificate(cert_path, password)

        # Create temp directory for PEM files
        temp_dir = tempfile.mkdtemp(prefix='efactura_cert_')

        # Write certificate PEM
        cert_pem_path = os.path.join(temp_dir, 'cert.pem')
        with open(cert_pem_path, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # Write key PEM (without encryption - it's in a temp file)
        key_pem_path = os.path.join(temp_dir, 'key.pem')
        with open(key_pem_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        # Set restrictive permissions on key file
        os.chmod(key_pem_path, 0o600)

        # Track for cleanup
        self._temp_files.extend([cert_pem_path, key_pem_path, temp_dir])

        logger.debug(
            "Created temporary PEM files",
            extra={'temp_dir_hash': hashlib.sha256(temp_dir.encode()).hexdigest()[:8]}
        )

        return cert_pem_path, key_pem_path

    def get_cert_for_session(
        self,
        cert_path: str,
        password: str,
    ) -> str:
        """
        Get certificate in format suitable for requests.Session.

        For PKCS12, this creates a combined PEM file.

        Args:
            cert_path: Path to PKCS12 certificate
            password: Certificate password

        Returns:
            Path to combined PEM file (cert + key)
        """
        cert, private_key, cert_info = self.load_certificate(cert_path, password)

        # Create combined PEM file
        temp_dir = tempfile.mkdtemp(prefix='efactura_cert_')
        combined_pem_path = os.path.join(temp_dir, 'combined.pem')

        with open(combined_pem_path, 'wb') as f:
            # Write certificate
            f.write(cert.public_bytes(serialization.Encoding.PEM))
            # Write private key
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        os.chmod(combined_pem_path, 0o600)
        self._temp_files.extend([combined_pem_path, temp_dir])

        return combined_pem_path

    def store_certificate(
        self,
        company_cif: str,
        cert_data: bytes,
        password: str,
    ) -> Dict[str, Any]:
        """
        Store certificate securely for a company.

        This method validates the cert and prepares it for secure storage.
        Actual storage implementation depends on vault configuration.

        Args:
            company_cif: Company tax ID
            cert_data: PKCS12 certificate bytes
            password: Certificate password (stored separately)

        Returns:
            Dict with storage info and certificate metadata
        """
        # Validate certificate first
        _, _, cert_info = self.load_certificate_from_bytes(cert_data, password)

        # Create fingerprint for identification
        cert_hash = hashlib.sha256(cert_data).hexdigest()

        logger.info(
            "Storing certificate for company",
            extra={
                'cif': company_cif,
                'cert_fingerprint': cert_info.fingerprint_sha256[:16],
                'expires': cert_info.not_after.isoformat(),
            }
        )

        # Return metadata for storage layer
        return {
            'cif': company_cif,
            'cert_hash': cert_hash,
            'fingerprint': cert_info.fingerprint_sha256,
            'subject': cert_info.subject,
            'organization': cert_info.organization,
            'expires_at': cert_info.not_after.isoformat(),
            'is_valid': True,
        }

    def cleanup(self):
        """Clean up temporary certificate files."""
        import shutil

        for path in self._temp_files:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.unlink(path)
            except OSError as e:
                logger.warning(
                    "Failed to cleanup temp file",
                    extra={'error': str(e)}
                )

        self._temp_files.clear()
        logger.debug("Cleaned up temporary certificate files")

    def __del__(self):
        """Cleanup on garbage collection."""
        self.cleanup()
