"""
e-Factura Repositories

Database access layer for e-Factura entities.
Uses raw psycopg2 following JARVIS conventions.
"""

from .company_repo import CompanyConnectionRepository
from .invoice_repository import EFacturaInvoiceRepository
from .supplier_mapping_repository import SupplierMappingRepository
from .supplier_type_repository import SupplierTypeRepository
from .sync_repo import SyncRepository
from .oauth_repository import OAuthRepository

__all__ = [
    'CompanyConnectionRepository',
    'EFacturaInvoiceRepository',
    'SupplierMappingRepository',
    'SupplierTypeRepository',
    'SyncRepository',
    'OAuthRepository',
]
