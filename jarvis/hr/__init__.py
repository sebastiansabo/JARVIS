"""JARVIS HR Section.

This section contains all HR-related applications:
- Events: Employee event and bonus management

Future apps may include:
- Payroll
- Recruitment
- Performance reviews
"""
from flask import Blueprint, redirect, url_for

# Section-level blueprint
hr_bp = Blueprint('hr', __name__)

# Register apps within section
from .events import events_bp  # noqa: E402
hr_bp.register_blueprint(events_bp, url_prefix='/events')


@hr_bp.route('/')
def index():
    """Redirect to the default HR app (Events)."""
    return redirect(url_for('hr.events.event_bonuses'))
