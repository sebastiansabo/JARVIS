"""Approval engine module."""
from flask import Blueprint

approvals_bp = Blueprint('approvals', __name__)

from . import routes  # noqa: E402, F401
