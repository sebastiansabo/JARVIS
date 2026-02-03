"""
RO e-Factura Accounting Module

Provides the accounting-focused e-Factura interface with unallocated invoices
management and integration with the JARVIS Invoice Module.
"""

from flask import Blueprint

# Create blueprint for accounting e-Factura routes
# Note: Different name and prefix to avoid conflict with core/connectors/efactura
accounting_efactura_bp = Blueprint(
    'accounting_efactura',
    __name__,
    url_prefix='/accounting/efactura',
    template_folder='templates'
)

# Import routes after blueprint creation to avoid circular imports
from . import routes  # noqa: F401, E402

__all__ = ['accounting_efactura_bp']
