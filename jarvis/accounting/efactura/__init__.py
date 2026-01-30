"""
RO e-Factura Connector Module

Provides integration with ANAF's e-Factura system for receiving and sending
electronic invoices in Romania. Uses X.509 certificate-based authentication.
"""

from flask import Blueprint

# Create main blueprint for e-Factura routes
efactura_bp = Blueprint(
    'efactura',
    __name__,
    url_prefix='/efactura',
    template_folder='templates'
)

# Import routes after blueprint creation to avoid circular imports
from . import routes  # noqa: F401, E402

__all__ = ['efactura_bp']
