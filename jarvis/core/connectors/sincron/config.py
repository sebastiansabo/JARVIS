"""Sincron connector configuration."""

BASE_URL = 'https://sincron.biz/v2.7.9/api/v1/autoworld/timesheet'
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
PAGE_SIZE = 50  # Sincron returns 50 employees per page

# Company names are resolved dynamically from connectors.config.company_tokens.
