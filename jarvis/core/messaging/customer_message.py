"""Provider-agnostic outbound message to an external customer.

MVP supports 'email' only (transactional SMTP via notification_service). An
'sms' adapter can be added later without changing callers. Customer emails set
skip_global_cc=True so prospects are never CC'd to the internal global address.
"""
from core.services.notification_service import send_email


def send_customer_message(channel, to, subject, body_html, body_text=None, from_name=None):
    """`from_name` overrides the sender's display name (the address stays the
    authenticated SMTP mailbox) — e.g. an event's "<Brand> Test Drive" instead of
    the default "Jarvis"."""
    if channel == 'email':
        return send_email(to, subject, body_html, body_text, from_name=from_name, skip_global_cc=True)
    return False, f'unsupported channel: {channel}'
