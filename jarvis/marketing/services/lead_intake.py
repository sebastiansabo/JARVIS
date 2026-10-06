"""Webhook lead payload normalization.

Takes the free-form JSON an external system (Zapier) POSTs and produces a
clean dict ready for ``ProjectLeadRepository.create``. Keeps a whitelist of
known columns; everything else is preserved under ``raw_payload`` so no data
is lost and future fields need no code change.
"""

# Lead lifecycle (mirrors the mkt_project_leads.status CHECK constraint).
LEAD_STATUSES = ('new', 'contacted', 'qualified', 'converted', 'discarded')

# Scalar fields mapped to dedicated columns. Order is not significant.
KNOWN_FIELDS = (
    'contact_name', 'phone', 'email', 'company_name', 'cui',
    'source', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'message', 'model_of_interest',
)

# Identity: a lead must carry at least one of these to be actionable.
_IDENTITY_FIELDS = ('contact_name', 'phone', 'email')

_MAX_LEN = 2000  # per-field cap; the full original still lives in raw_payload


def _clean(value):
    """Trim to a non-empty string capped at _MAX_LEN, or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text[:_MAX_LEN] if text else None


def normalize_lead_payload(data: dict) -> dict:
    """Validate + normalize a webhook body.

    Raises ValueError if the payload is not a dict or carries no identity
    (name/phone/email). Returns a dict of the known fields plus ``phone_raw``
    (the original phone as sent) and ``raw_payload`` (the untouched body).
    """
    if not isinstance(data, dict):
        raise ValueError('Lead payload must be a JSON object')

    out = {field: _clean(data.get(field)) for field in KNOWN_FIELDS}

    if not any(out.get(field) for field in _IDENTITY_FIELDS):
        raise ValueError('Lead requires at least one of: contact_name, phone, email')

    raw_phone = data.get('phone')
    out['phone_raw'] = str(raw_phone) if raw_phone is not None else None
    out['raw_payload'] = data
    return out
