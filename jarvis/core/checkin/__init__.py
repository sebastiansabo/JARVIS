"""GPS Mobile Check-in Module."""

from flask import Blueprint

checkin_bp = Blueprint('checkin', __name__, url_prefix='/mobile-checkin')

from . import routes  # noqa: F401, E402

__all__ = ['checkin_bp']
