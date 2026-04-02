"""Sincron connector configuration."""

BASE_URL = 'https://sincron.biz/v2.7.9/api/v1/autoworld/timesheet'
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
PAGE_SIZE = 50  # Sincron returns 50 employees per page

# Company names expected — tokens are stored in the connectors table (JSONB config)
COMPANY_NAMES = [
    'AUTOWORLD S.R.L.',
    'AUTOWORLD INSURANCE S.R.L.',
    'AUTOWORLD INTERNATIONAL S.R.L.',
    'AUTOWORLD NEXT S.R.L.',
    'AUTOWORLD ONE S.R.L.',
    'AUTOWORLD PLUS S.R.L.',
    'AUTOWORLD PREMIUM S.R.L.',
    'AUTOWORLD PRESTIGE S.R.L.',
]
