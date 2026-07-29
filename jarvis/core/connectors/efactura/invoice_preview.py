"""
Build a JSON-serialisable preview of an e-Factura invoice from its stored UBL XML.

Reads only local data (the XML we already hold in `efactura_invoices.xml_content`) via the
existing `parse_invoice_xml` — it makes NO ANAF calls, so the in-app preview works even when
ANAF's transformare/PDF service is unavailable.
"""
from datetime import date
from decimal import Decimal

from .models import InvoiceLineItem, ParsedInvoice
from .xml_parser import parse_invoice_xml


def _num(value) -> str:
    """Render a Decimal/number as a plain, full-precision string for display."""
    if value is None:
        return "0"
    return format(Decimal(value), 'f')


def _iso(value):
    return value.isoformat() if isinstance(value, date) else None


def _line_dict(li: InvoiceLineItem) -> dict:
    return {
        'line_number': li.line_number,
        'description': li.description,
        'quantity': _num(li.quantity),
        'unit': li.unit,
        'unit_price': _num(li.unit_price),
        'line_amount': _num(li.line_amount),
        'vat_rate': _num(li.vat_rate),
        'vat_amount': _num(li.vat_amount),
        'seller_item_id': li.seller_item_id,
        'buyer_item_id': li.buyer_item_id,
        'commodity_code': li.commodity_code,
    }


def parsed_invoice_to_dict(inv: ParsedInvoice) -> dict:
    """Serialise a ParsedInvoice into the preview payload consumed by the frontend modal."""
    return {
        'invoice_number': inv.invoice_number,
        'invoice_series': inv.invoice_series,
        'issue_date': _iso(inv.issue_date),
        'due_date': _iso(inv.due_date),
        'currency': inv.currency,
        'seller': {
            'name': inv.seller_name,
            'cif': inv.seller_cif,
            'address': inv.seller_address,
            'reg_number': inv.seller_reg_number,
        },
        'buyer': {
            'name': inv.buyer_name,
            'cif': inv.buyer_cif,
            'address': inv.buyer_address,
        },
        'totals': {
            'without_vat': _num(inv.total_without_vat),
            'vat': _num(inv.total_vat),
            'total': _num(inv.total_amount),
        },
        'vat_breakdown': [
            {
                'rate': _num(b.get('rate')),
                'taxable': _num(b.get('taxable')),
                'amount': _num(b.get('amount')),
            }
            for b in inv.vat_breakdown
        ],
        'line_items': [_line_dict(li) for li in inv.line_items],
        'payment': {
            'means': inv.payment_means,
            'terms': inv.payment_terms,
            'bank_account': inv.bank_account,
        },
        'note': inv.invoice_note,
    }


def build_invoice_preview(xml_content: str) -> dict:
    """Parse stored UBL XML into a JSON-serialisable preview dict (no ANAF, no PDF)."""
    return parsed_invoice_to_dict(parse_invoice_xml(xml_content))
