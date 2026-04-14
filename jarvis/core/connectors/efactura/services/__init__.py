"""
e-Factura Services
"""
from .base import ServiceResult
from .invoice_service import InvoiceService
from .efactura_service import EFacturaService
from .sync_service import EFacturaSyncService
from .invoice_allocation_service import InvoiceAllocationService
from .invoice_visibility_service import InvoiceVisibilityService
from .duplicate_service import DuplicateDetectionService
from .pdf_service import PDFService
from .oauth_service import ANAFOAuthService, OAuthTokens, get_oauth_service


def get_certificate_auth_service():
    """Get CertificateAuthService (lazy import to avoid cryptography dependency)."""
    from .auth_service import CertificateAuthService
    return CertificateAuthService


__all__ = [
    'get_certificate_auth_service',
    'ServiceResult',
    'InvoiceService',
    'EFacturaService',
    'EFacturaSyncService',
    'InvoiceAllocationService',
    'InvoiceVisibilityService',
    'DuplicateDetectionService',
    'PDFService',
    'ANAFOAuthService',
    'OAuthTokens',
    'get_oauth_service',
]
