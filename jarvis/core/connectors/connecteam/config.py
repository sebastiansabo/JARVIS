"""Connecteam connector configuration."""

OAUTH_TOKEN_URL = 'https://api.connecteam.com/oauth/v1/token'
WEBHOOK_API_URL = 'https://api.connecteam.com/settings/v1/webhooks'
API_BASE_URL = 'https://api.connecteam.com'
REQUEST_TIMEOUT = 15
TOKEN_EXPIRY_SECONDS = 86400   # 24 hours
TOKEN_REFRESH_BUFFER = 3600    # Refresh 1 hour before expiry

# Target form
BILET_INVOIRE_FORM_ID = 952672
BILET_INVOIRE_FORM_NAME = 'Bilet de Invoire'

# Webhook event types we handle
SUPPORTED_EVENT_TYPES = ['form_submission', 'form_submission_edited']
