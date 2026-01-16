"""JARVIS Core Settings Routes.

Platform settings management routes - will be populated from app.py migration.
For now, settings routes remain in app.py for backward compatibility.
"""
from flask import render_template, jsonify, request
from flask_login import login_required, current_user

from . import settings_bp


# Settings routes will be migrated here from app.py
# For now, they remain in app.py for backward compatibility
