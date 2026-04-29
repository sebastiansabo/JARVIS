"""Proforma Service — orchestrates load → validate → generate proforma PDFs.

No EuroFib xlsx generation for proforma flow.
"""
import logging
from dataclasses import dataclass
from typing import Any

from ..loaders.anexa import load_anexa
from ..models import OrderLine

logger = logging.getLogger("jarvis.facturare.proforma_service")


@dataclass
class ProformaResult:
    success: bool
    lines_count: int = 0
    proforma_pdf: bytes | None = None
    total_amount: float = 0.0
    proforma_range: str = ""
    error: str | None = None
    validation_report: dict[str, Any] | None = None


class ProformaService:
    """Orchestrates the proforma pipeline (no EuroFib)."""

    def validate(self, supplier: dict, customer: dict, start_no: int,
                 invoice_date: str, anexa_bytes: bytes,
                 sheet_name: str = "Sheet1") -> ProformaResult:
        """Load and validate proforma Anexa. Returns sanity report."""
        try:
            lines = load_anexa(anexa_bytes, sheet_name=sheet_name)

            total = sum(l.advance for l in lines)
            models: dict[str, dict] = {}
            for l in lines:
                models.setdefault(l.model, {"count": 0, "total": 0.0})
                models[l.model]["count"] += 1
                models[l.model]["total"] += l.advance

            last_no = start_no + len(lines) - 1

            return ProformaResult(
                success=True,
                lines_count=len(lines),
                total_amount=total,
                proforma_range=f"{start_no}–{last_no}",
                validation_report={
                    "row_count": len(lines),
                    "total_amount": round(total, 2),
                    "proforma_range": f"{start_no}–{last_no}",
                    "models": {
                        k: {"count": v["count"], "total": round(v["total"], 2)}
                        for k, v in models.items()
                    },
                    "currency": "EUR",
                },
            )
        except Exception as e:
            logger.error(f"Proforma validation failed: {e}", exc_info=True)
            return ProformaResult(success=False, error=str(e))

    def generate(self, supplier: dict, customer: dict, start_no: int,
                 invoice_date: str, intocmit_de: str,
                 anexa_bytes: bytes, sheet_name: str = "Sheet1") -> ProformaResult:
        """Load Anexa → generate proforma PDF bytes."""
        try:
            lines = load_anexa(anexa_bytes, sheet_name=sheet_name)

            total = sum(l.advance for l in lines)
            last_no = start_no + len(lines) - 1

            from ..generators.proforma_pdf import ProformaPdfRenderer
            renderer = ProformaPdfRenderer(
                supplier=supplier,
                customer=customer,
                invoice_date=invoice_date,
                intocmit_de=intocmit_de,
            )
            pdf_bytes = renderer.render_all_to_bytes(lines, start_no)
            logger.info(f"Generated {len(lines)} proforma PDFs")

            return ProformaResult(
                success=True,
                lines_count=len(lines),
                proforma_pdf=pdf_bytes,
                total_amount=total,
                proforma_range=f"{start_no}–{last_no}",
            )

        except Exception as e:
            logger.error(f"Proforma generation failed: {e}", exc_info=True)
            return ProformaResult(success=False, error=str(e))
