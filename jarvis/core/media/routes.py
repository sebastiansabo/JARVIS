"""Authenticated media proxy — streams private Spaces objects to logged-in users.

Only serves the non-sensitive prefixes below. Signatures / driver-license
images are NOT served here — they go through their module's permissioned
endpoints or PDF generation only.
"""
import logging
from flask import Blueprint, Response, abort
from flask_login import login_required
from core.services import spaces_service

logger = logging.getLogger('jarvis.core.media')
media_bp = Blueprint('media', __name__)

_ALLOWED_PREFIXES = ('private/carpark/', 'private/logos/', 'private/foi-parcurs/damage/')


@media_bp.route('/api/media/<path:key>', methods=['GET'])
@login_required
def get_media(key):
    if not key.startswith(_ALLOWED_PREFIXES):
        abort(403)
    try:
        data, content_type = spaces_service.fetch(key)
    except Exception:
        logger.warning('Media fetch failed for key=%s', key)
        abort(404)
    return Response(data, mimetype=content_type,
                     headers={'Cache-Control': 'private, max-age=86400'})
