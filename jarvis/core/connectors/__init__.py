"""
JARVIS Core Connectors

External system connectors available across all JARVIS sections.
Each connector provides integration with third-party APIs and services.

Available Connectors:
- efactura: Romanian e-Factura (ANAF) integration
"""

from .efactura import efactura_bp

__all__ = ['efactura_bp']
