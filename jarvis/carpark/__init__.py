"""CarPark module — Vehicle inventory management for Autoworld HOLDING.

Blueprint: carpark_bp, mounted at /api/carpark
"""
from flask import Blueprint

carpark_bp = Blueprint('carpark', __name__, url_prefix='/api/carpark')

# Import routes to register them on the blueprint
from .routes import vehicles, photos, costs  # noqa: F401, E402
