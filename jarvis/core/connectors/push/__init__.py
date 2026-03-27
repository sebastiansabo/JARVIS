"""Push Notification Connector — Firebase Cloud Messaging integration."""

from flask import Blueprint

push_bp = Blueprint('push', __name__, url_prefix='/push')

from . import routes  # noqa: F401, E402

__all__ = ['push_bp']
