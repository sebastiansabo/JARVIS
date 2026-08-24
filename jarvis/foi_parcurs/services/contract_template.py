"""Render a per-company contract body_template by substituting a whitelisted
set of {placeholders} with session data. Plain, safe string replacement — no
eval, no user SQL. Unknown {tokens} are left as-is so authors see their typos;
a whitelisted token with no value renders empty."""

# Whitelisted tokens an author may use in a contract template.
PLACEHOLDERS = (
    'client_name', 'client_phone', 'client_address',
    'company_name', 'brand', 'vin', 'registration_number',
    'km_start', 'km_end', 'distance_km',
    'departure_datetime', 'return_datetime',
    'service_order_ref', 'advisor_name', 'general_conditions',
)


def render_contract_template(template: str, context: dict) -> str:
    """Substitute only whitelisted {tokens}; leave unknown {tokens} literal."""
    if not template:
        return ''
    out = template
    ctx = context or {}
    for token in PLACEHOLDERS:
        needle = '{' + token + '}'
        if needle in out:
            value = ctx.get(token)
            out = out.replace(needle, '' if value is None else str(value))
    return out
