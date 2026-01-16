"""Bugetare Invoice Routes.

Part of JARVIS Accounting Section > Bugetare Application.

Routes for invoice management, allocation, and reporting.
Note: Currently routes remain in main app.py for backward compatibility.
This file will be populated as routes are migrated from app.py.
"""
from flask import render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user

from . import bugetare_bp


# Invoice routes will be migrated here from app.py
# For now, they remain in app.py for backward compatibility
