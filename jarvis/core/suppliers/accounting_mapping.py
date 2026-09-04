"""Invoice → accounting (EuroFib) posting-field mapping — pure, config-driven.

See docs/superpowers/plans/2026-09-04-suppliers-master-phase1_1.md ("Mapping function") for
the exact rules this implements verbatim. `config` is expected to be an *effective* Table-2
konto dict for the invoice's (supplier, company) — see
`SupplierMasterRepository.get_effective_konto()`.

Never hardcodes account numbers, never guesses a missing value, never int()'s an account/cost
centre code (they may carry leading zeros, e.g. "0393").
"""

# Config keys copied verbatim (coalescing None -> "") into the output.
_FIXED_FIELDS = (
    'klient', 'konto_debit', 'konto_credit', 'gegenkonto_debit', 'gegenkonto_credit',
    'kostenstelle_debit', 'kostenstelle_credit',
)

# Output dict key order (also the full set of keys always present in the result).
_OUTPUT_KEYS = (
    'konto_debit', 'konto_credit', 'klient', 'gegenkonto_debit', 'gegenkonto_credit',
    'kostenstelle_debit', 'kostenstelle_credit', 'extbeleg_debit', 'extbeleg_credit',
)


def map_invoice_to_accounting_fields(invoice: dict, config: dict) -> dict:
    """Map an invoice + its effective Table-2 config to the 9 EuroFib posting fields.

    invoice: {supplier, supplier_id?, invoice_number, invoice_date, due_date,
              net_amount, vat_amount, gross_amount}
    config: an effective supplier_konto_config dict (see
            SupplierMasterRepository.get_effective_konto) for the invoice's company.

    Rules:
    - No Table 2 config (falsy) -> raise ValueError (never guess).
    - If both config['supplier_id'] and invoice['supplier_id'] are given and differ -> raise
      ValueError (the config must belong to the detected supplier).
    - Fixed fields are copied from config, coalescing None -> "".
    - extbeleg_credit = invoice['invoice_number'] if config.get('extbeleg_credit') ==
      'invoice_number' else "". Same rule for extbeleg_debit.
    - All outputs are strings (never int() — leading zeros must survive).

    Returns a dict with exactly these keys: konto_debit, konto_credit, klient,
    gegenkonto_debit, gegenkonto_credit, kostenstelle_debit, kostenstelle_credit,
    extbeleg_debit, extbeleg_credit.
    """
    if not config:
        supplier_id = (invoice or {}).get('supplier_id', '?')
        raise ValueError(f"No Table 2 config for supplier {supplier_id}")

    config_supplier_id = config.get('supplier_id')
    invoice_supplier_id = (invoice or {}).get('supplier_id')
    if config_supplier_id is not None and invoice_supplier_id is not None \
            and config_supplier_id != invoice_supplier_id:
        raise ValueError(
            f"Table 2 config belongs to supplier {config_supplier_id}, "
            f"not the invoice's supplier {invoice_supplier_id}")

    fields = {}
    for key in _FIXED_FIELDS:
        value = config.get(key)
        fields[key] = '' if value is None else str(value)

    invoice_number = invoice.get('invoice_number')
    invoice_number_str = '' if invoice_number is None else str(invoice_number)

    fields['extbeleg_credit'] = invoice_number_str if config.get('extbeleg_credit') == 'invoice_number' else ''
    fields['extbeleg_debit'] = invoice_number_str if config.get('extbeleg_debit') == 'invoice_number' else ''

    return {key: fields[key] for key in _OUTPUT_KEYS}
