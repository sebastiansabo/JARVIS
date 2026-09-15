"""Cost Centers module — Finance budgeting dimension (kostenstelle)."""
from flask import Blueprint

cost_centers_bp = Blueprint('cost_centers', __name__)

from . import routes  # noqa: E402, F401
