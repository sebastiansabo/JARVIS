"""JARVIS buyback module.

Exposes the buyback blueprint and registers route decorators.
"""
from flask import Blueprint

buyback_bp = Blueprint('buyback', __name__, url_prefix='/api/buyback')

# Ruling R1 (Task 9): routes now exist — import unconditionally so a broken
# route module fails loudly at app startup instead of being silently
# swallowed.
from . import routes  # noqa: F401,E402  (registers route decorators)
