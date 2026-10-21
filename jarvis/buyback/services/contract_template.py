"""Render a buyback contract template by substituting a whitelisted
set of {placeholders} with context data. Plain, safe string replacement — no
eval, no user SQL. Unknown {tokens} are left as-is so authors see their typos;
a whitelisted token with no value renders empty."""

# Whitelisted tokens an author may use in a buyback contract template.
PLACEHOLDERS = (
    'contract_number', 'contract_date', 'company_name', 'company_address',
    'company_reg_no', 'company_vat', 'company_administrator', 'company_iban',
    'company_bank', 'advisor_name', 'seller_name', 'seller_address',
    'seller_cnp', 'seller_cui', 'seller_ci', 'seller_reg_no',
    'seller_legal_rep', 'brand', 'model', 'vin', 'engine_no',
    'engine_capacity', 'power_cp', 'civ_no', 'mileage', 'first_registration',
    'manufacture_date', 'price_eur', 'price_ron', 'price_words', 'vat_note',
    'owner_price', 'min_price', 'promo_price', 'commission', 'monthly_fee',
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
