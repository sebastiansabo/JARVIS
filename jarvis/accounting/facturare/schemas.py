"""Pydantic v2 schemas for the Facturare invoice storage.

Entity hierarchy: Contract → Anexa (with vehicles) → Invoices (lifecycle docs).
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Contract ─────────────────────────────────────────────────────

class ContractCreateRequest(BaseModel):
    contract_ref: str
    supplier_id: int
    customer_id: int
    contract_date: Optional[date] = None
    responsible: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("contract_ref")
    @classmethod
    def validate_ref(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("contract_ref cannot be empty")
        return v


# ── Anexa ────────────────────────────────────────────────────────

class AnexaLineCreate(BaseModel):
    nr_comanda: Optional[str] = None
    vin: str = ""
    model: str
    culoare: Optional[str] = None
    list_price_eur: Decimal = Decimal("0")
    selling_price_eur: Decimal = Decimal("0")
    qty: int = 1


class AnexaCreateRequest(BaseModel):
    contract_id: int
    anexa_number: int = Field(ge=1)
    lines: list[AnexaLineCreate]
    notes: Optional[str] = None

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one vehicle line required")
        return v


# ── Invoice lifecycle ────────────────────────────────────────────

class ProformaCreateRequest(BaseModel):
    anexa_id: int
    amount_eur: Decimal = Field(gt=0)
    split_mode: str = "equal"  # "equal" or "proportional"
    invoice_number: Optional[int] = Field(None, ge=1, le=9999999)
    issued_date: Optional[date] = None
    intocmit_de: Optional[str] = None
    notes: Optional[str] = None
    line_ids: Optional[list[int]] = None  # selected anexa line IDs (None = all lines)
    doc_mode: str = "per_car"  # "per_car" or "single_doc"


class InvoiceCreateRequest(BaseModel):
    anexa_id: int
    sequence_number: int = Field(ge=1)
    invoice_number: Optional[int] = Field(None, ge=1, le=9999999)
    issued_date: Optional[date] = None
    intocmit_de: Optional[str] = None
    notes: Optional[str] = None
    doc_mode: str = "per_car"  # "per_car" or "single_doc"


class StornoCreateRequest(BaseModel):
    anexa_id: int
    invoice_number: Optional[int] = Field(None, ge=1, le=9999999)
    issued_date: Optional[date] = None
    intocmit_de: Optional[str] = None
    notes: Optional[str] = None
    line_ids: Optional[list[int]] = None


class FinalCreateRequest(BaseModel):
    anexa_id: int
    invoice_number: Optional[int] = Field(None, ge=1, le=9999999)
    issued_date: Optional[date] = None
    intocmit_de: Optional[str] = None
    notes: Optional[str] = None
    line_ids: Optional[list[int]] = None
