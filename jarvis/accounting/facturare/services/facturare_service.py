"""Facturare Service — orchestrates load → validate → generate."""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import JobConfig
from ..loaders.anexa import load_anexa
from ..models import OrderLine

logger = logging.getLogger("jarvis.facturare.service")


@dataclass
class GenerationResult:
    success: bool
    lines_count: int = 0
    invoices_pdf: bytes | None = None
    eurofib_xlsx: bytes | None = None
    total_advance: float = 0.0
    invoice_range: str = ""
    error: str | None = None
    validation_report: dict[str, Any] | None = None


class FacturareService:
    """Orchestrates the full facturare pipeline."""

    @staticmethod
    def _invoice_range(cfg: JobConfig, lines: list[OrderLine]) -> str:
        """Compute display range accounting for per-row overrides."""
        inv_nos = []
        for i, line in enumerate(lines):
            inv_nos.append(line.start_no if line.start_no is not None else cfg.invoice.start_no + i)
        if not inv_nos:
            return ""
        mn, mx = min(inv_nos), max(inv_nos)
        return str(mn) if mn == mx else f"{mn}–{mx}"

    def validate(self, cfg: JobConfig, anexa_bytes: bytes) -> GenerationResult:
        """Load and validate Anexa + config. Returns a sanity report, no files."""
        try:
            lines = load_anexa(anexa_bytes, sheet_name=cfg.input.sheet)
            has_row_overrides = any(l.start_no is not None for l in lines)
            if not has_row_overrides:
                cfg.validate_invoice_range(len(lines))

            total_advance = sum(l.advance * l.qty for l in lines)
            models = {}
            for l in lines:
                models.setdefault(l.model, {"count": 0, "total": 0.0})
                models[l.model]["count"] += 1
                models[l.model]["total"] += l.advance * l.qty

            inv_range = self._invoice_range(cfg, lines)
            storno_count = sum(1 for l in lines if l.qty < 0)

            return GenerationResult(
                success=True,
                lines_count=len(lines),
                total_advance=total_advance,
                invoice_range=inv_range,
                validation_report={
                    "row_count": len(lines),
                    "total_advance": round(total_advance, 2),
                    "invoice_range": inv_range,
                    "storno_count": storno_count,
                    "models": {
                        k: {"count": v["count"], "total": round(v["total"], 2)}
                        for k, v in models.items()
                    },
                    "currency": cfg.fx.currency,
                    "kurs": cfg.fx.kurs,
                },
            )
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            return GenerationResult(success=False, error=str(e))

    def generate(self, cfg: JobConfig, anexa_bytes: bytes,
                 generate_pdf: bool = True,
                 generate_xlsx: bool = True) -> GenerationResult:
        """Run the full pipeline: load → validate → generate PDF + xlsx."""
        try:
            lines = load_anexa(anexa_bytes, sheet_name=cfg.input.sheet)
            has_row_overrides = any(l.start_no is not None for l in lines)
            if not has_row_overrides:
                cfg.validate_invoice_range(len(lines))

            total_advance = sum(l.advance * l.qty for l in lines)
            inv_range = self._invoice_range(cfg, lines)

            pdf_bytes = None
            xlsx_bytes = None

            if generate_pdf:
                from ..generators.invoice_pdf import InvoicePdfRenderer
                pdf_renderer = InvoicePdfRenderer(cfg)
                pdf_bytes = pdf_renderer.render_all_to_bytes(lines)
                logger.info(f"Generated {len(lines)} invoice PDFs")

            if generate_xlsx:
                from ..generators.eurofib_xlsx import EurofibXlsxRenderer
                xlsx_renderer = EurofibXlsxRenderer(cfg)
                xlsx_bytes = xlsx_renderer.render_to_bytes(lines)
                logger.info(f"Generated EuroFib xlsx with {len(lines) * 2} rows")

            return GenerationResult(
                success=True,
                lines_count=len(lines),
                invoices_pdf=pdf_bytes,
                eurofib_xlsx=xlsx_bytes,
                total_advance=total_advance,
                invoice_range=inv_range,
            )

        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            return GenerationResult(success=False, error=str(e))

    def generate_to_disk(self, cfg: JobConfig, base_dir: Path) -> GenerationResult:
        """File-based generation (for CLI / local use). Reads Anexa from disk."""
        try:
            anexa_path = base_dir / cfg.input.anexa
            if not anexa_path.exists():
                return GenerationResult(
                    success=False, error=f"Anexa file not found: {anexa_path}"
                )

            lines = load_anexa(str(anexa_path), sheet_name=cfg.input.sheet)
            has_row_overrides = any(l.start_no is not None for l in lines)
            if not has_row_overrides:
                cfg.validate_invoice_range(len(lines))

            paths = cfg.resolve_paths(base_dir)
            total_advance = sum(l.advance * l.qty for l in lines)
            inv_range = self._invoice_range(cfg, lines)

            from ..generators.invoice_pdf import InvoicePdfRenderer
            pdf_renderer = InvoicePdfRenderer(cfg)
            pdf_path = pdf_renderer.render_all(lines, paths["invoices_pdf"])
            logger.info(f"Wrote {len(lines)} invoices to {pdf_path}")

            from ..generators.eurofib_xlsx import EurofibXlsxRenderer
            xlsx_renderer = EurofibXlsxRenderer(cfg)
            xlsx_path = xlsx_renderer.render(lines, paths["eurofib_xlsx"])
            logger.info(f"Wrote EuroFib xlsx to {xlsx_path}")

            return GenerationResult(
                success=True,
                lines_count=len(lines),
                total_advance=total_advance,
                invoice_range=inv_range,
            )

        except Exception as e:
            logger.error(f"Disk generation failed: {e}", exc_info=True)
            return GenerationResult(success=False, error=str(e))
