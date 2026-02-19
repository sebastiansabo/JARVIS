"""JARVIS Core Services Module.

Shared services used across all platform sections:
- Google Drive integration
- Email notifications
- Image compression
- Currency conversion
- Settings management
"""

from .settings_service import SettingsService

__all__ = [
    'SettingsService',
]
