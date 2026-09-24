"""JARVIS buyback module.

Exposes the buyback blueprint and registers route decorators when available.
"""
from flask import Blueprint

buyback_bp = Blueprint('buyback', __name__, url_prefix='/api/buyback')

try:
    from . import routes  # noqa: F401  (registers route decorators once the package exists)
except ImportError:
    pass
