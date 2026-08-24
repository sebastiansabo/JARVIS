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
    # S4: client identity + company legal + Service pricing snapshot tokens
    # used by service_contract_templates.py.
    'client_ci_serie', 'client_company', 'client_cui', 'client_email',
    'company_administrator', 'company_bank', 'company_city', 'company_county',
    'company_email', 'company_iban', 'company_reg_no', 'company_street',
    'company_vat', 'dealer_phone', 'vehicle_model',
    'svc_extra_km_eur', 'svc_fransiza_eur', 'svc_garantie_eur',
    'svc_limita_km_zi', 'svc_rate_basis', 'svc_tariff_eur', 'svc_total_eur',
    'svc_units',
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
