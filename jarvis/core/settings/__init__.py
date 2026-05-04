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

# Routes are imported explicitly in app.py after blueprint creation to avoid
# circular imports via schema_misc → core.settings → routes → base_repository → database
