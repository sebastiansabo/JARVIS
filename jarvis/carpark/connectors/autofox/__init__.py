"""AutoFox.ai connector — inbound delivery of AI-processed vehicle photos.

AutoFox pushes finished images to the customer's system (DMS/CRM) keyed on
VIN. JARVIS exposes a token-authenticated webhook that AutoFox calls; the
service resolves the vehicle by VIN, downloads/compresses each image, stores
it in private Spaces and records it in carpark_vehicle_photos.
"""
from flask import Blueprint

autofox_bp = Blueprint('autofox', __name__, url_prefix='/autofox')

from . import routes  # noqa: E402, F401

__all__ = ['autofox_bp']
