"""Bugetare - Invoice Budget Allocation Application.

Part of JARVIS Accounting Section.

Features:
- Invoice parsing (AI and template-based)
- Department allocation management
- Bulk invoice processing
- Google Drive integration
"""
from flask import Blueprint

bugetare_bp = Blueprint('bugetare', __name__,
                        template_folder='../../templates/accounting/bugetare')

# Import routes to register them
from . import routes  # noqa: E402, F401
