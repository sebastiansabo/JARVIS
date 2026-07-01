"""Data models for the Facturare module."""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal


# ── Existing Anexa models (unchanged — used by PDF generators) ───

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
    contract_ref: str | None = None
    anexa_ref: str | None = None
    start_no: int | None = None
    invoice_date: str | None = None
    qty: int = 1
    kurs: float | None = None
    storno_description: str | None = None
    kostenstelle: str | None = None
    konto_credit_override: str | None = None


InvoiceKind = Literal["invoice", "proforma"]


# ── Invoice storage enums ────────────────────────────────────────

class InvoiceTypeEnum(str, Enum):
    PROFORMA = "PROFORMA"
    INVOICE = "INVOICE"
    STORNO = "STORNO"
    FINAL = "FINAL"
    STORNO_SPLIT = "STORNO_SPLIT"


class InvoiceStateEnum(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class InvoiceLinkTypeEnum(str, Enum):
    REVERSES = "REVERSES"
    PRECEDES = "PRECEDES"
    REPLACES = "REPLACES"
    SPLITS = "SPLITS"


# ── Contract ─────────────────────────────────────────────────────

@dataclass
class StoredContract:
    id: int
    contract_ref: str
    supplier_id: int
    customer_id: int
    contract_date: date | None
    responsible: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None

    @classmethod
    def from_row(cls, row: dict) -> "StoredContract":
        return cls(
            id=row["id"], contract_ref=row["contract_ref"],
            supplier_id=row["supplier_id"], customer_id=row["customer_id"],
            contract_date=row.get("contract_date"),
            responsible=row.get("responsible"), notes=row.get("notes"),
            created_at=row["created_at"], updated_at=row["updated_at"],
            created_by=row.get("created_by"),
        )


# ── Anexa ────────────────────────────────────────────────────────

@dataclass
class StoredAnexa:
    id: int
    contract_id: int
    anexa_number: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
    lines: list["StoredAnexaLine"] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict) -> "StoredAnexa":
        return cls(
            id=row["id"], contract_id=row["contract_id"],
            anexa_number=row["anexa_number"], notes=row.get("notes"),
            created_at=row["created_at"], updated_at=row["updated_at"],
            created_by=row.get("created_by"),
        )


@dataclass
class StoredAnexaLine:
    id: int
    anexa_id: int
    line_number: int
    model: str
    list_price_eur: Decimal
    selling_price_eur: Decimal
    qty: int
    nr_comanda: str | None = None
    vin: str | None = None
    culoare: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> "StoredAnexaLine":
        return cls(
            id=row["id"], anexa_id=row["anexa_id"],
            line_number=row["line_number"], model=row["model"],
            list_price_eur=Decimal(str(row["list_price_eur"])),
            selling_price_eur=Decimal(str(row["selling_price_eur"])),
            qty=row["qty"],
            nr_comanda=row.get("nr_comanda"), vin=row.get("vin"),
            culoare=row.get("culoare"),
        )


# ── Invoice (lighter — references anexa) ─────────────────────────

@dataclass
class StoredInvoice:
    id: int
    anexa_id: int
    invoice_type: InvoiceTypeEnum
    invoice_state: InvoiceStateEnum
    sequence_number: int
    total_amount_eur: Decimal
    total_amount_ron: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime
    invoice_number: int | None = None
    issued_date: date | None = None
    kurs_applied: Decimal | None = None
    intocmit_de: str | None = None
    notes: str | None = None
    created_by: int | None = None

    @classmethod
    def from_row(cls, row: dict) -> "StoredInvoice":
        return cls(
            id=row["id"], anexa_id=row["anexa_id"],
            invoice_type=InvoiceTypeEnum(row["invoice_type"]),
            invoice_state=InvoiceStateEnum(row["invoice_state"]),
            sequence_number=row.get("sequence_number", 1),
            total_amount_eur=Decimal(str(row["total_amount_eur"])),
            total_amount_ron=Decimal(str(row["total_amount_ron"])),
            currency=row["currency"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            invoice_number=row.get("invoice_number"),
            issued_date=row.get("issued_date"),
            kurs_applied=Decimal(str(row["kurs_applied"])) if row.get("kurs_applied") else None,
            intocmit_de=row.get("intocmit_de"), notes=row.get("notes"),
            created_by=row.get("created_by"),
        )
