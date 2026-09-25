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


def per_car_number(base_no, doc_mode, line_ids, line_id, stored=None):
    """The concrete number the document for one car (``line_id``) carries.

    Prefers ``stored`` — the ``{line_id: document_number}`` map persisted at
    issue time (``facturare_document_numbers``) — and falls back to the same
    positional rule ``allocate`` uses, but over THIS document's own ``line_ids``
    order (``base_no + position``, or ``base_no`` for ``single_doc``).

    Used to print a *proforma's* per-car number on the advance invoice that
    confirms it: the reference must match the number that specific car carries
    on the proforma, not the advance invoice's own page index — which is what
    the naive ``base_no + page_index`` derivation produced (JAR: Aurento /
    CTR-338 showed base 1290 for a car whose proforma number was 1302).
    """
    if stored and line_id in stored:
        return stored[line_id]
    if base_no is None:
        return None
    if doc_mode == "single_doc":
        return base_no
    if line_ids and line_id in line_ids:
        return base_no + line_ids.index(line_id)
    return base_no
