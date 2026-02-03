"""
e-Factura Connector Configuration

Defines configuration schema, environment variables, and UI field definitions
for the RO e-Factura ANAF integration.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Environment(Enum):
    """ANAF API environments."""
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class ANAFConfig:
    """ANAF API configuration settings."""

    # API endpoints
    PRODUCTION_BASE_URL: str = "https://api.anaf.ro/prod/FCTEL/rest"
    TEST_BASE_URL: str = "https://api.anaf.ro/test/FCTEL/rest"

    # OAuth endpoints (for SPV portal token refresh)
    OAUTH_URL: str = "https://logincert.anaf.ro/anaf-oauth2/v1"

    # Rate limiting
    MAX_REQUESTS_PER_HOUR: int = 150
    RATE_LIMIT_BUFFER: int = 10  # Reserve buffer from max

    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 2.0  # seconds
    RETRY_MAX_DELAY: float = 30.0  # seconds

    # Connection settings
    REQUEST_TIMEOUT: int = 30  # seconds
    DOWNLOAD_TIMEOUT: int = 120  # seconds for large ZIP files

    # Certificate settings
    CERT_EXPIRY_WARNING_DAYS: int = 30

    # Sync settings
    SYNC_LOOKBACK_DAYS: int = 7  # Safety window for missed invoices
    MAX_MESSAGES_PER_PAGE: int = 100
    DEFAULT_SYNC_INTERVAL_HOURS: int = 1

    # Storage settings
    ARTIFACT_STORAGE_PATH: str = "efactura"  # Base path in storage
    MAX_ARTIFACT_SIZE_MB: int = 50

    def get_base_url(self, environment: Environment) -> str:
        """Get API base URL for the specified environment."""
        if environment == Environment.PRODUCTION:
            return self.PRODUCTION_BASE_URL
        return self.TEST_BASE_URL


@dataclass
class ConnectorConfig:
    """Full connector configuration loaded from environment."""

    # Environment
    environment: Environment = field(default=Environment.TEST)

    # Certificate paths (loaded from env or vault)
    cert_path: Optional[str] = None
    cert_password: Optional[str] = None
    cert_base64: Optional[str] = None  # For production env var storage

    # Database
    database_url: Optional[str] = None

    # Storage
    artifact_storage_type: str = "local"  # local, s3, gcs, drive
    artifact_storage_config: dict = field(default_factory=dict)

    # Feature flags
    enable_sent_invoices: bool = True
    enable_auto_sync: bool = True
    enable_notifications: bool = False

    @classmethod
    def from_env(cls) -> 'ConnectorConfig':
        """Load configuration from environment variables."""
        return cls(
            environment=Environment(
                os.environ.get('EFACTURA_ENVIRONMENT', 'test')
            ),
            cert_path=os.environ.get('EFACTURA_CERT_PATH'),
            cert_password=os.environ.get('EFACTURA_CERT_PASSWORD'),
            cert_base64=os.environ.get('EFACTURA_CERT_BASE64'),
            database_url=os.environ.get('DATABASE_URL'),
            artifact_storage_type=os.environ.get(
                'EFACTURA_STORAGE_TYPE', 'local'
            ),
            artifact_storage_config={
                'base_path': os.environ.get(
                    'EFACTURA_STORAGE_PATH',
                    '/tmp/efactura_artifacts'
                ),
                's3_bucket': os.environ.get('EFACTURA_S3_BUCKET'),
                's3_prefix': os.environ.get('EFACTURA_S3_PREFIX', 'efactura/'),
            },
            enable_sent_invoices=os.environ.get(
                'EFACTURA_ENABLE_SENT', 'true'
            ).lower() == 'true',
            enable_auto_sync=os.environ.get(
                'EFACTURA_ENABLE_AUTO_SYNC', 'true'
            ).lower() == 'true',
            enable_notifications=os.environ.get(
                'EFACTURA_ENABLE_NOTIFICATIONS', 'false'
            ).lower() == 'true',
        )


# UI Configuration for Settings page
UI_CONFIG = {
    'name': 'RO e-Factura',
    'description': 'Integration with ANAF e-Factura system for electronic invoices',
    'icon': 'file-invoice',
    'fields': [
        {
            'key': 'environment',
            'label': 'Environment',
            'type': 'select',
            'options': [
                {'value': 'test', 'label': 'Test (Sandbox)'},
                {'value': 'production', 'label': 'Production'},
            ],
            'required': True,
            'help': 'Select ANAF API environment',
        },
        {
            'key': 'company_cif',
            'label': 'Company CIF',
            'type': 'text',
            'required': True,
            'help': 'Company tax identification number (without RO prefix)',
            'validation': r'^\d{2,10}$',
        },
        {
            'key': 'certificate',
            'label': 'Digital Certificate (.p12/.pfx)',
            'type': 'file',
            'accept': '.p12,.pfx',
            'required': True,
            'help': 'ANAF-registered digital certificate file',
        },
        {
            'key': 'certificate_password',
            'label': 'Certificate Password',
            'type': 'password',
            'required': True,
            'help': 'Password to decrypt the certificate',
        },
        {
            'key': 'sync_interval',
            'label': 'Sync Interval (hours)',
            'type': 'number',
            'min': 1,
            'max': 24,
            'default': 1,
            'help': 'How often to check for new invoices',
        },
        {
            'key': 'enable_sent',
            'label': 'Sync Sent Invoices',
            'type': 'checkbox',
            'default': True,
            'help': 'Also fetch invoices sent by this company',
        },
    ],
}


# API Response Status Codes
class ANAFStatus:
    """ANAF API response status codes."""
    OK = "ok"
    ERROR = "nok"
    PENDING = "in prelucrare"
    INVALID = "invalid"


# Invoice Direction
class InvoiceDirection(Enum):
    """Direction of invoice relative to company."""
    RECEIVED = "received"  # Primite
    SENT = "sent"  # Trimise


# Invoice Status in e-Factura system
class EFacturaStatus(Enum):
    """Status of invoice in ANAF system."""
    UPLOADED = "uploaded"  # Uploaded, awaiting processing
    VALID = "valid"  # XML validated successfully
    INVALID = "invalid"  # Validation failed
    PROCESSED = "processed"  # Fully processed
    ERROR = "error"  # System error


# Artifact types
class ArtifactType(Enum):
    """Types of stored artifacts."""
    ZIP = "zip"  # Original ZIP from ANAF
    XML = "xml"  # Extracted invoice XML
    PDF = "pdf"  # Generated or attached PDF
    SIGNATURE = "signature"  # Digital signature file
    RESPONSE = "response"  # ANAF response XML


# Default configuration instance
DEFAULT_CONFIG = ANAFConfig()
