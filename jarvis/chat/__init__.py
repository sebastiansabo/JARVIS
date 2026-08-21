"""Chat / Communication Module (formerly Digest)."""
from flask import Blueprint

chat_bp = Blueprint('chat', __name__)

from .routes import *  # noqa: E402, F401
