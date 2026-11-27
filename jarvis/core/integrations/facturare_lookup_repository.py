"""Read-only facturare (Comenzi Externe) invoice lookup for first-party integrations.

Resolves, for a batch of order numbers (``nr_comanda``), every facturare invoice
document attached to that order's anexa line(s). The order→invoice link is the
jsonb ``facturare_invoices.line_ids`` array containing the
``facturare_anexa_lines.id``. A line with no invoice is returned once with NULL
invoice fields (LEFT JOIN), so callers can tell "ordered, not invoiced" apart
from "order unknown".
"""
from core.base_repository import BaseRepository


class FacturareLookupRepository(BaseRepository):
    """Batch nr_comanda → facturare invoice-document reads. Read-only."""

    def by_order_numbers(self, order_numbers: list) -> list:
        """Rows for every (anexa line × its invoices) whose trimmed nr_comanda is
        in ``order_numbers``. One row per invoice document; a line with no invoice
        yields a single row with NULL invoice fields. Orders with no line are
        simply absent from the result.
        """
        orders = [o.strip() for o in order_numbers if o and o.strip()]
        if not orders:
            return []
        return self.query_all(
            """
            SELECT btrim(al.nr_comanda) AS nr_comanda, al.vin, al.model, al.id AS line_id,
                   i.invoice_number, i.invoice_type, i.issued_date,
                   i.total_amount_eur, i.total_amount_ron, i.currency, i.archived
            FROM facturare_anexa_lines al
            LEFT JOIN facturare_invoices i ON i.line_ids @> to_jsonb(al.id)
            WHERE btrim(al.nr_comanda) = ANY(%s)
            """,
            (orders,),
        ) or []
