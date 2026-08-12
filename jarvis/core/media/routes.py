"""Authenticated media proxy — streams private Spaces objects to logged-in users.

Only serves the non-sensitive prefixes below. Signatures / driver-license
images are NOT served here — they go through their module's permissioned
endpoints or PDF generation only.

Security: the proxy serves objects from JARVIS's OWN origin, so it must never
render active content inline (an object stored with Content-Type text/html or
image/svg+xml would otherwise execute script in our origin → stored XSS). We
therefore:
  * only serve a raster-image allowlist inline (correct type);
  * force everything else to download as application/octet-stream;
  * send X-Content-Type-Options: nosniff and a locked-down CSP on EVERY response.
"""
import logging
import re
from flask import Blueprint, Response, abort
from flask_login import login_required
from core.services import spaces_service

logger = logging.getLogger('jarvis.core.media')
media_bp = Blueprint('media', __name__)

_ALLOWED_PREFIXES = ('private/carpark/', 'private/logos/', 'private/foi-parcurs/damage/')

# Only these raster image types are ever served inline from our own origin.
# Everything else (text/html, image/svg+xml, application/*, ...) is forced to
# download so it can never execute script in JARVIS's origin.
_INLINE_IMAGE_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif',
})

# Applied to EVERY response (inline image or forced download).
_SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; sandbox",
}


def _safe_filename(key):
    """Basename of the key, sanitized so it can't inject into the header."""
    name = key.rsplit('/', 1)[-1] or 'download'
    # Drop anything that isn't a safe filename character (also kills quotes,
    # backslashes and CR/LF so it can't break out of the header value).
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
    return name or 'download'


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

    headers = dict(_SECURITY_HEADERS)
    headers['Cache-Control'] = 'private, max-age=86400'

    ctype = (content_type or '').split(';', 1)[0].strip().lower()
    if ctype in _INLINE_IMAGE_TYPES:
        return Response(data, mimetype=ctype, headers=headers)

    # Non-image / potentially-active content: never serve inline from our
    # origin — force the browser to download it instead.
    headers['Content-Disposition'] = f'attachment; filename="{_safe_filename(key)}"'
    return Response(data, mimetype='application/octet-stream', headers=headers)
