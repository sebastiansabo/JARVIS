"""Digest / Communication Module."""
from flask import Blueprint

digest_bp = Blueprint('digest', __name__)

from .routes import *  # noqa: E402, F401
