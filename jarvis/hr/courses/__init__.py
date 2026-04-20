"""HR Courses Application.

Part of JARVIS HR Section.

Features:
- Course management and tracking
- Employee enrollment
- Certification tracking with expiry
"""
from flask import Blueprint

courses_bp = Blueprint('courses', __name__)

# Import routes to register them
from . import routes  # noqa: E402, F401
