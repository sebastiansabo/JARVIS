"""JARVIS Mobile API Module.

JWT authentication and mobile-optimized endpoints for the JARVIS mobile app.
"""
from flask import Blueprint

mobile_bp = Blueprint('mobile', __name__)

from . import routes  # noqa: E402, F401
