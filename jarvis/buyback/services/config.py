"""Effective per-tenant buyback notification config (row-or-defaults)."""
import os

from buyback.repositories.config_repository import ConfigRepository

DEFAULT_ACQUISITION_EMAIL = 'achizitii@autoworld.ro'

_repo = ConfigRepository()

_BOOL_DEFAULTS = {
    'enabled': True,
    'channel_email': True, 'channel_in_app': True, 'channel_push': True,
    'notify_new_request': True, 'notify_milestones': True, 'notify_inspection': True,
}


def _parse_emails(raw) -> list[str]:
    if not raw:
        return []
    return [e.strip() for e in str(raw).replace(';', ',').split(',') if e.strip()]


def _default_acquisition_emails() -> list[str]:
    env = (os.environ.get('BUYBACK_ACQUISITION_EMAIL') or '').strip()
    return _parse_emails(env) if env else [DEFAULT_ACQUISITION_EMAIL]


def get_config(company_id) -> dict:
    try:
        row = _repo.get(company_id) if company_id is not None else None
    except Exception:
        row = None
    cfg = dict(_BOOL_DEFAULTS)
    if row:
        for k in _BOOL_DEFAULTS:
            if row.get(k) is not None:
                cfg[k] = bool(row[k])
        cfg['acquisition_emails'] = _parse_emails(row.get('acquisition_emails')) or _default_acquisition_emails()
    else:
        cfg['acquisition_emails'] = _default_acquisition_emails()
    return cfg
