"""Shared imports for ticketing routes."""
from flask import request, jsonify, g  # noqa: F401
from flask_login import login_required, current_user  # noqa: F401

from ticketing import ticketing_bp  # noqa: F401
from ticketing.repositories.ticket_repository import TicketRepository, TicketCommentRepository  # noqa: F401
from core.utils.api_helpers import error_response, safe_error_response, get_json_or_error  # noqa: F401
from core.roles.decorators import v2_permission_required  # noqa: F401
from core.notifications.notify import notify_user  # noqa: F401
