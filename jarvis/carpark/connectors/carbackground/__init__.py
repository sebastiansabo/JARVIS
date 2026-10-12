"""CarBackground.ai connector — AI background replacement for vehicle photos."""
from flask import Blueprint

carbackground_bp = Blueprint('carbackground', __name__, url_prefix='/carbackground')

from . import routes  # noqa: E402,F401

__all__ = ['carbackground_bp']
