"""Convert a project lead into a CRM client.

Pure orchestration over an injected CRM client repository so it is unit-testable
without a DB.

Reuse only happens on a STRONG identifier the lead itself supplied — phone or
fiscal code (cui/nr_reg). A name-only match is deliberately NOT used to reuse an
existing client: two unrelated people/companies can share a name, and auto-
linking on that would attach the project (and the existing client's deals) to
the wrong record. When no strong identifier matches, a new client is created.
"""


def _display_name(lead):
    """Best available human label for the client, or '' if the lead is empty."""
    for key in ('contact_name', 'company_name', 'email', 'phone'):
        value = (lead.get(key) or '').strip()
        if value:
            return value
    return ''


def resolve_or_create_client(client_repo, lead):
    """Find an existing CRM client by STRONG identifier, else create one.

    Returns (client_id, created: bool). Raises ValueError when the lead carries
    no identity to build a client from.
    """
    name = _display_name(lead)
    if not name:
        raise ValueError('Lead has no contact name, company, email or phone to create a client')

    phone = (lead.get('phone') or '').strip() or None
    if phone:
        existing = client_repo.find_by_phone(phone)
        if existing:
            return existing['id'], False

    cui = (lead.get('cui') or '').strip() or None
    if cui:
        existing = client_repo.find_by_nr_reg(cui)
        if existing:
            return existing['id'], False

    row = client_repo.create_from_form({
        'display_name': name,
        'client_type': 'person' if (lead.get('contact_name') or '').strip() else 'company',
        'phone': phone,
        'email': (lead.get('email') or '').strip() or None,
        'company_name': (lead.get('company_name') or '').strip() or None,
        'cui': cui,
    })
    if not row:
        raise ValueError('Failed to create CRM client from lead')
    return row['id'], True
