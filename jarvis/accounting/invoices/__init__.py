"""Invoices & allocations domain."""
from flask import Blueprint

invoices_bp = Blueprint('invoices', __name__)

from . import routes  # noqa: E402, F401
