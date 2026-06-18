"""Controlling BAB — BAB import and Marja margin reports."""
from flask import Blueprint

controlling_bab_bp = Blueprint('controlling_bab', __name__)

from . import routes  # noqa: E402, F401
