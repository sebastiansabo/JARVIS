"""Resilient invoice parsing for the CarPark invoice->cost/income flow.

Wraps accounting's `parse_invoice_from_bytes` with a PDF-repair retry. Some
supplier / internal invoices ("COPIE FACTURA INTERNA" dumps and the like) ship
a structurally-broken PDF — a bad cross-reference table / missing trailer — that
a viewer tolerates but poppler (which pdf2image uses to rasterize the page for
the vision parser) refuses, so the first parse raises and the user sees "couldn't
read the invoice". pikepdf (qpdf) reconstructs the xref into a clean PDF that
renders, so we repair and retry once.
"""
import io
import logging

logger = logging.getLogger('jarvis.carpark')


def _looks_like_pdf(file_bytes: bytes, filename: str) -> bool:
    return (filename or '').lower().endswith('.pdf') or file_bytes[:5] == b'%PDF-'


def repair_pdf_bytes(file_bytes: bytes) -> bytes:
    """Rewrite a structurally-broken PDF into a clean one poppler can render.

    pikepdf opens with qpdf's automatic recovery (reconstructs a damaged xref /
    trailer) and re-serialises. Raises if the PDF is too damaged to recover.
    """
    import pikepdf  # lazy: only paid on the repair path
    with pikepdf.open(io.BytesIO(file_bytes)) as pdf:
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def parse_invoice_resilient(file_bytes: bytes, filename: str) -> dict:
    """Parse an invoice into the parser's field dict.

    First tries the file as-is; if that raises and the file is a PDF, repairs
    the PDF (pikepdf) and retries once. Re-raises if both attempts fail — the
    caller (parse-invoice route) degrades that to a blank dialog.
    """
    # Lazy import: the AI parser pulls in the LLM client + poppler, which we
    # don't want paid at blueprint-registration time.
    from accounting.bugetare.invoice_parser import parse_invoice_from_bytes
    try:
        return parse_invoice_from_bytes(file_bytes, filename)
    except Exception as first_err:
        if not _looks_like_pdf(file_bytes, filename):
            raise
        logger.warning(
            f'Invoice parse failed ({first_err}); retrying with a pikepdf-repaired PDF'
        )
        repaired = repair_pdf_bytes(file_bytes)  # raises if unrecoverable
        return parse_invoice_from_bytes(repaired, filename)
