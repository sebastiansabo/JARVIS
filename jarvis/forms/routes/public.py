"""Public form routes — NO authentication required."""

import logging
import time
from collections import defaultdict

from flask import jsonify, request

from forms import forms_bp
from forms.repositories import FormRepository
from forms.services.form_service import FormService

logger = logging.getLogger('jarvis.forms.routes.public')

_form_repo = FormRepository()
_service = FormService()

# In-memory rate limiter: {ip: [timestamp, ...]}
_submit_timestamps: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60       # seconds
_RATE_LIMIT_MAX_REQUESTS = 5  # per IP per window


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded the submission rate limit."""
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW
    # Prune old entries
    _submit_timestamps[ip] = [t for t in _submit_timestamps[ip] if t > cutoff]
    if len(_submit_timestamps[ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        return True
    _submit_timestamps[ip].append(now)
    return False


def _get_client_ip() -> str:
    """Extract client IP from request, handling proxy headers."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip or '0.0.0.0'


@forms_bp.route('/public/<slug>', methods=['GET'])
def api_get_public_form(slug):
    """Get a published form by slug (no auth). Returns form schema + settings."""
    form = _form_repo.get_by_slug(slug)
    if not form:
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    return jsonify({
        'id': form['id'],
        'name': form['name'],
        'slug': form['slug'],
        'description': form.get('description'),
        'schema': form.get('published_schema', []),
        'settings': form.get('settings', {}),
        'branding': form.get('branding', {}),
        'utm_config': form.get('utm_config', {}),
        'company_name': form.get('company_name', ''),
    })


@forms_bp.route('/public/<slug>/submit', methods=['POST'])
def api_submit_public_form(slug):
    """Submit a response to a public form (no auth)."""
    ip = _get_client_ip()

    # Rate limit check
    if _is_rate_limited(ip):
        return jsonify({'success': False, 'error': 'Too many submissions. Please try again later.'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    # Enforce max body size check (answers shouldn't be enormous)
    if request.content_length and request.content_length > 1_048_576:  # 1 MB
        return jsonify({'success': False, 'error': 'Request too large'}), 413

    answers = data.get('answers', {})
    utm_data = data.get('utm_data', {})
    respondent_info = {
        'name': data.get('respondent_name'),
        'email': data.get('respondent_email'),
        'phone': data.get('respondent_phone'),
    }

    result = _service.submit_public(slug, answers, utm_data, respondent_info, ip)

    if result.success:
        return jsonify({'success': True, **result.data}), result.status_code
    return jsonify({'success': False, 'error': result.error}), result.status_code
