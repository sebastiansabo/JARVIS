"""JARVIS Core Authentication Module.

Handles user authentication, roles, and permissions across the platform.
"""
from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from . import routes  # noqa: E402, F401
