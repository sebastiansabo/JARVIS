"""Pydantic v2 schema for facturare job YAML configs."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


class ContractConfig(BaseModel):
    ref: str
    anexa_ref: str


class InputConfig(BaseModel):
    anexa: str
    sheet: str = "Sheet1"


class InvoiceConfig(BaseModel):
    kind: Literal["invoice", "proforma"] = "invoice"
    start_no: int
    date: date
    intocmit_de: str = "Ilona Foszto"
    description_prefix: str = "1. ADVANCE PAYMENT"

    @field_validator("start_no")
    @classmethod
    def invoice_no_range(cls, v):
        if v <= 0 or v >= 10_000_000:
            raise ValueError("start_no must be between 1 and 9,999,999")
        return v


class FxConfig(BaseModel):
    currency: str = "EUR"
    kurs: float
    kurs_date: date

    @field_validator("kurs")
    @classmethod
    def kurs_positive(cls, v):
        if v <= 0:
            raise ValueError("kurs must be positive")
        return v


class PartyConfig(BaseModel):
    name: str
    address_lines: list[str]
    reg_no: str | None = None
    vat: str | None = None
    iban: str | None = None
    bank: str | None = None
    swift: str | None = None


class EurofibConfig(BaseModel):
    klient: int
    konto_debit: int
    konto_credit: int
    belegart: str = "JVV"
    steuercode: str = "L00"
    fw_steuercode: str = "L00"
    text_template: str = "avans {brand_short} {comanda}"
    brand_map: dict[str, str] = {}


class OutputConfig(BaseModel):
    invoices_pdf: str = "out/{job_id}_invoices.pdf"
    eurofib_xlsx: str = "out/{job_id}_eurofib.xlsx"
    per_invoice_pdfs: bool = False


class JobConfig(BaseModel):
    """Top-level facturare job configuration."""
    job_id: str
    contract: ContractConfig
    input: InputConfig
    invoice: InvoiceConfig
    fx: FxConfig
    supplier: PartyConfig
    customer: PartyConfig
    eurofib: EurofibConfig
    output: OutputConfig = OutputConfig()

    def resolve_paths(self, base_dir: Path) -> dict[str, Path]:
        """Resolve output path placeholders and make absolute."""
        replacements = {
            "{job_id}": self.job_id,
            "{date}": self.invoice.date.strftime("%Y-%m-%d"),
        }
        result = {}
        for key in ("invoices_pdf", "eurofib_xlsx"):
            raw = getattr(self.output, key)
            for k, v in replacements.items():
                raw = raw.replace(k, v)
            result[key] = (base_dir / raw).resolve()
        return result

    def validate_invoice_range(self, row_count: int):
        """Ensure invoice numbers stay within EuroFib's 7-digit limit."""
        last_no = self.invoice.start_no + row_count - 1
        if last_no >= 10_000_000:
            raise ValueError(
                f"Invoice range {self.invoice.start_no}–{last_no} "
                f"exceeds EuroFib 7-digit limit"
            )

    @classmethod
    def from_yaml(cls, path: Path) -> "JobConfig":
        """Load and validate a YAML config file."""
        import yaml
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)
