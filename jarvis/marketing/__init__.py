"""Marketing Projects Module."""
from flask import Blueprint

marketing_bp = Blueprint('marketing', __name__)

from .routes import projects, budget, events, social, dashboard, admin, simulator, okr, dms_links, client_links, ai_generate  # noqa: E402, F401
