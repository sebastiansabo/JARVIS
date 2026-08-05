"""Pure allocation of per-document (per-car) invoice numbers.

The invoice record stores one user-entered base number + doc_mode. This turns
that into the concrete number each car's document carries — the single rule that
all consumers (eurofib, PDF, UI) and the backfill share.
"""

_FISCAL_TYPES = {"INVOICE", "STORNO", "FINAL"}


def series_for(invoice_type: str) -> str:
    return "fiscal" if invoice_type in _FISCAL_TYPES else "proforma"


def allocate(invoice_type, base_no, doc_mode, line_ids):
    series = series_for(invoice_type)
    single = doc_mode == "single_doc"
    out = []
    for position, line_id in enumerate(line_ids):
        if base_no is None:
            number = None
        else:
            number = base_no if single else base_no + position
        out.append({
            "line_id": line_id,
            "position": position,
            "document_number": number,
            "series": series,
        })
    return out
