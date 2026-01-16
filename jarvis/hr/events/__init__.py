"""HR Events Application.

Part of JARVIS HR Section.

Features:
- Employee management
- Event tracking
- Bonus calculation and management
"""
from flask import Blueprint

events_bp = Blueprint('events', __name__,
                      template_folder='../../templates/hr/events')

# Import routes to register them
from . import routes  # noqa: E402, F401
