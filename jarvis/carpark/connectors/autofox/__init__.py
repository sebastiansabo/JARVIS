"""AutoFox.ai connector — read-only pull of AI-processed vehicle photos.

Colleagues photograph and process cars in the AutoFox app; JARVIS pulls the
finished images from AutoFox's REST API (see client.py), matched to a vehicle
by VIN, and stores them in private Spaces + carpark_vehicle_photos. Driven
on demand from the CarPark "Sincronizează din AutoFox" picker.
"""
from flask import Blueprint

autofox_bp = Blueprint('autofox', __name__, url_prefix='/autofox')

from . import routes  # noqa: E402, F401

__all__ = ['autofox_bp']
