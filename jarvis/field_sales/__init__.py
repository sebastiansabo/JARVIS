"""JARVIS Field Sales / KAM — visit planning, client enrichment, fleet registry."""
from flask import Blueprint

field_sales_bp = Blueprint('field_sales', __name__)

from . import routes  # noqa: E402, F401
