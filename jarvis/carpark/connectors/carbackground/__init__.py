"""CarBackground.ai connector — AI background replacement for vehicle photos.

Task 3 creates this package's Blueprint ONLY. Do NOT add `from . import
routes` here — routes.py doesn't exist until Task 5, and importing it now
would ImportError and break the Task 3/4 client/service unit tests.
"""
from flask import Blueprint

carbackground_bp = Blueprint('carbackground', __name__, url_prefix='/carbackground')

__all__ = ['carbackground_bp']
