"""
JARVIS Core Connectors

External system connectors available across all JARVIS sections.
Each connector provides integration with third-party APIs and services.

Available Connectors:
- efactura: Romanian e-Factura (ANAF) integration
"""
from flask import Blueprint

connectors_bp = Blueprint('connectors_ui', __name__)

from .efactura import efactura_bp  # noqa: E402
from .biostar import biostar_bp  # noqa: E402
from . import routes  # noqa: E402, F401

__all__ = ['efactura_bp', 'biostar_bp', 'connectors_bp']
