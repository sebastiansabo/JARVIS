"""JARVIS Core Settings Module.

Platform-wide settings management:
- Themes
- Dropdown options
- VAT rates
- Organization structure
- Companies
- Responsables
- Notification settings
"""
from flask import Blueprint

settings_bp = Blueprint('settings', __name__, template_folder='../../templates/core')

from . import routes  # noqa: E402, F401
