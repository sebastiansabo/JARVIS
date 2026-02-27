"""Document Management System Module."""
from flask import Blueprint

dms_bp = Blueprint('dms', __name__)

from .routes import documents, files, categories, rel_types, parties, party_roles, signatures, extraction, drive_sync, suppliers  # noqa: F401, E402
