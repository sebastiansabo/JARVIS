"""Shopify connector — publishes CarPark vehicles to a Shopify store."""
from flask import Blueprint

shopify_bp = Blueprint('shopify', __name__, url_prefix='/shopify')

from . import routes  # noqa: E402, F401

__all__ = ['shopify_bp']
