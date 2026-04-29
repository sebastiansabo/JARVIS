"""Data models for the Facturare module."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OrderLine:
    """Single row from an Anexa xlsx — one vehicle order."""
    comanda: int
    model: str
    culoare: str
    list_price: float | None
    selling_price: float | None
    advance: float
    rest: float | None
    vin: str | None = None
    # Per-row overrides (from proforma Anexa columns F-I)
    contract_ref: str | None = None
    anexa_ref: str | None = None
    start_no: int | None = None
    invoice_date: str | None = None


InvoiceKind = Literal["invoice", "proforma"]
