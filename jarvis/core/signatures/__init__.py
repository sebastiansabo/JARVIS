"""Digital signature module."""
from flask import Blueprint

signatures_bp = Blueprint('signatures', __name__)

from . import routes  # noqa: E402, F401
