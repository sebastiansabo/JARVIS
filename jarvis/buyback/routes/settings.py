"""Admin-only per-tenant buyback notification config routes.

GET  /api/buyback/settings/config?company_id=<id>  -> resolved config
PUT  /api/buyback/settings/config                  -> upsert (validates emails)

Both @login_required + admin-only (current_user.can_access_settings). The
config is edited by a global admin via a company switcher in the Settings tab.
"""
import re

from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.repositories.config_repository import ConfigRepository
from buyback.services.config import get_config

_config_repo = ConfigRepository()
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_BOOL_FIELDS = (
    'enabled', 'channel_email', 'channel_in_app', 'channel_push',
    'notify_new_request', 'notify_milestones', 'notify_inspection',
)


def _require_admin():
    if not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'Admin permission required'}), 403
    return None


def _company_id_from(source, key='company_id'):
    try:
        return int(source.get(key))
    except (TypeError, ValueError):
        return None


def _serialize(company_id):
    cfg = get_config(company_id)
    cfg['company_id'] = company_id
    cfg['acquisition_emails'] = ', '.join(cfg['acquisition_emails'])
    return cfg


@buyback_bp.route('/settings/config', methods=['GET'])
@login_required
def get_settings_config():
    err = _require_admin()
    if err:
        return err
    company_id = _company_id_from(request.args)
    if company_id is None:
        return jsonify({'success': False, 'error': 'company_id required'}), 400
    return jsonify({'config': _serialize(company_id)})


@buyback_bp.route('/settings/config', methods=['PUT'])
@login_required
def put_settings_config():
    err = _require_admin()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    company_id = _company_id_from(data)
    if company_id is None:
        return jsonify({'success': False, 'error': 'company_id required'}), 400

    fields = {b: bool(data[b]) for b in _BOOL_FIELDS if b in data}
    if 'acquisition_emails' in data:
        emails = [e.strip() for e in str(data['acquisition_emails']).replace(';', ',').split(',') if e.strip()]
        for e in emails:
            if not _EMAIL_RE.match(e):
                return jsonify({'success': False, 'error': f'Invalid email: {e}'}), 400
        fields['acquisition_emails'] = ', '.join(emails)

    _config_repo.upsert(company_id, fields, updated_by=current_user.id)
    return jsonify({'success': True, 'config': _serialize(company_id)})
