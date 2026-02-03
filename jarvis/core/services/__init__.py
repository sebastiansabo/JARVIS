"""JARVIS Core Services Module.

Shared services used across all platform sections:
- Google Drive integration
- Email notifications
- Image compression
- Currency conversion
- Invoice management
- Settings management
"""

from .invoice_service import InvoiceService
from .settings_service import SettingsService

__all__ = [
    'InvoiceService',
    'SettingsService',
]
