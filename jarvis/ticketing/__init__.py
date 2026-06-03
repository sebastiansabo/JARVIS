"""Technical Ticketing (IT Helpdesk) Module."""
from flask import Blueprint

ticketing_bp = Blueprint('ticketing', __name__)

from .routes import tickets  # noqa: F401, E402
