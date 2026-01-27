"""
e-Factura Services

Business logic services for the e-Factura connector.
"""

from .invoice_service import InvoiceService
from .efactura_service import EFacturaService
from .oauth_service import ANAFOAuthService, OAuthTokens, get_oauth_service

# CertificateAuthService requires cryptography - import lazily
def get_certificate_auth_service():
    """Get CertificateAuthService (lazy import to avoid cryptography dependency)."""
    from .auth_service import CertificateAuthService
    return CertificateAuthService

__all__ = [
    'get_certificate_auth_service',
    'InvoiceService',
    'EFacturaService',
    'ANAFOAuthService',
    'OAuthTokens',
    'get_oauth_service',
]
