"""Single source of truth for a buyback record's seller display name.

The seller is either a person (``client_type != 'company'``) whose name lives
in ``seller_name``, or a company whose firm name lives in ``seller_company_name``
with the representative in ``seller_legal_rep``. The two name columns are kept
mutually exclusive at the write boundary (see the frontend no-doubling
enforcement), but legacy company records created before the dedicated
``seller_company_name`` field stored the firm name in ``seller_name`` — the
fallback below keeps those rendering correctly.

Every contract, PDF, email, notification, list view and the CarPark hand-off
must agree on which name to show, so they all route through this helper.
"""


def seller_display_name(record) -> str:
    """The seller's display name: the firm for a company seller (falling back
    to a legacy firm name in ``seller_name``), else the person's name. Never
    raises on a sparse/empty record; returns '' when nothing is set."""
    record = record or {}
    company = (record.get('seller_company_name') or '').strip()
    if record.get('client_type') == 'company' and company:
        return company
    return record.get('seller_name') or ''
