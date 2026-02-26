"""Document Management System Module."""
from flask import Blueprint

dms_bp = Blueprint('dms', __name__)

from .routes import documents, files, categories  # noqa: F401, E402
