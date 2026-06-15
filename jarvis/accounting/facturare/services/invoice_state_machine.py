"""Invoice State Machine — enforces the paired PROFORMA/INVOICE lifecycle per Anexa.

    PROFORMA 1 → INVOICE 1 (after payment)
    PROFORMA N → INVOICE N (after payment)
    STORNO (reverses all INVOICES)
    FINAL (full amount)

Entity hierarchy: Contract → Anexa → Invoices.
Vehicle lines live on the Anexa, not on invoices.
"""
import logging
from decimal import Decimal

from ..models import StoredInvoice, InvoiceTypeEnum, InvoiceStateEnum, InvoiceLinkTypeEnum
from ..repositories.invoice_storage_repository import InvoiceStorageRepository

logger = logging.getLogger("jarvis.facturare.state_machine")


class InvoiceStateMachineError(Exception):
    pass


class InvoiceStateMachine:

    def __init__(self, repo: InvoiceStorageRepository | None = None):
        self.repo = repo or InvoiceStorageRepository()

    def _resolve_intocmit(self, intocmit_de: str | None, user_id: int) -> str:
        if intocmit_de:
            return intocmit_de
        row = self.repo.query_one("SELECT name FROM users WHERE id = %s", (user_id,))
        return row["name"] if row else ""

    def _fetch_kurs(self, issued_date) -> Decimal | None:
        if not issued_date:
            return None
        try:
            from datetime import timedelta
            from core.services.currency_converter import get_exchange_rate
            kurs_date = issued_date - timedelta(days=1)
            rate = get_exchange_rate("EUR", kurs_date.strftime("%Y-%m-%d"))
            if rate:
                return Decimal(str(round(rate, 4)))
        except Exception as e:
            logger.warning("Failed to fetch BNR rate: %s", e)
        return None

    # ── Issue Proforma ───────────────────────────────────────────

    def issue_proforma(self, anexa_id: int, amount_eur: Decimal,
                       split_mode: str = "equal",
                       invoice_number: int | None = None, issued_date=None,
                       intocmit_de: str | None = None, notes: str | None = None,
                       created_by_user_id: int = 0) -> StoredInvoice:
        """Issue a Proforma for an Anexa."""
        # Check no STORNO yet
        existing_storno = self.repo.get_invoice_by_anexa_and_type(anexa_id, InvoiceTypeEnum.STORNO)
        if existing_storno:
            raise InvoiceStateMachineError("Cannot add proforma after STORNO")

        # Check amount doesn't exceed anexa total value
        anexa_lines = self.repo.get_lines_by_anexa(anexa_id)
        anexa_total = sum(Decimal(str(l["selling_price_eur"])) for l in anexa_lines)
        existing_proformas = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.PROFORMA)
        proformas_total = sum(Decimal(str(p["total_amount_eur"])) for p in existing_proformas)
        remaining = anexa_total - proformas_total

        if remaining <= 0:
            raise InvoiceStateMachineError(
                f"Anexa fully covered by existing proformas ({proformas_total} / {anexa_total} EUR)")

        if amount_eur > remaining:
            raise InvoiceStateMachineError(
                f"Amount {amount_eur} EUR exceeds remaining {remaining} EUR "
                f"(anexa: {anexa_total}, proformas: {proformas_total})")

        # All previous proformas must have their paired invoice before issuing a new one
        existing_invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)
        proforma_seqs = {p["sequence_number"] for p in existing_proformas}
        invoice_seqs = {i["sequence_number"] for i in existing_invoices}
        unpaired = proforma_seqs - invoice_seqs
        if unpaired:
            raise InvoiceStateMachineError(
                f"Proforma #{min(unpaired)} not yet invoiced — close existing proformas before issuing a new one")

        seq = len(existing_proformas) + 1
        kurs = self._fetch_kurs(issued_date)
        total_ron = (amount_eur * kurs) if kurs else Decimal("0")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.PROFORMA,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=seq,
            total_amount_eur=amount_eur,
            total_amount_ron=total_ron,
            kurs_applied=kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            split_mode=split_mode,
            notes=notes,
            created_by=created_by_user_id,
        )
        logger.info("Proforma #%d created: anexa=%s amount=%s EUR", seq, anexa_id, amount_eur)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Invoice ────────────────────────────────────────────

    def issue_invoice(self, anexa_id: int, sequence_number: int,
                      invoice_number: int | None = None, issued_date=None,
                      intocmit_de: str | None = None,
                      notes: str | None = None,
                      created_by_user_id: int = 0) -> StoredInvoice:
        """Issue an Invoice confirming payment of a specific Proforma."""
        proforma_row = self.repo.get_invoice_by_anexa_type_and_seq(
            anexa_id, InvoiceTypeEnum.PROFORMA, sequence_number)
        if not proforma_row:
            raise InvoiceStateMachineError(f"Proforma #{sequence_number} not found")

        existing = self.repo.get_invoice_by_anexa_type_and_seq(
            anexa_id, InvoiceTypeEnum.INVOICE, sequence_number)
        if existing:
            raise InvoiceStateMachineError(f"Invoice #{sequence_number} already exists")

        proforma_amount = Decimal(str(proforma_row["total_amount_eur"]))
        proforma_kurs = Decimal(str(proforma_row["kurs_applied"])) if proforma_row.get("kurs_applied") else None
        total_ron = (proforma_amount * proforma_kurs) if proforma_kurs else Decimal("0")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.INVOICE,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=sequence_number,
            total_amount_eur=proforma_amount,
            total_amount_ron=total_ron,
            kurs_applied=proforma_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes or f"Confirms Proforma #{sequence_number} (No: {proforma_row.get('invoice_number') or 'N/A'})",
            split_mode=proforma_row.get("split_mode", "equal"),
            created_by=created_by_user_id,
        )

        self.repo.create_link(
            source_invoice_id=proforma_row["id"],
            target_invoice_id=inv_row["id"],
            link_type=InvoiceLinkTypeEnum.PRECEDES,
        )

        logger.info("Invoice #%d created: anexa=%s amount=%s EUR", sequence_number, anexa_id, proforma_amount)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Storno ─────────────────────────────────────────────

    def issue_storno(self, anexa_id: int,
                     invoice_number: int | None = None, issued_date=None,
                     intocmit_de: str | None = None,
                     notes: str | None = None,
                     created_by_user_id: int = 0) -> StoredInvoice:
        """Issue a Storno reversing all INVOICES. All proformas must be invoiced first."""
        proformas = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.PROFORMA)
        if not proformas:
            raise InvoiceStateMachineError("No proformas found")

        invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)
        proforma_seqs = {r["sequence_number"] for r in proformas}
        invoice_seqs = {r["sequence_number"] for r in invoices}
        unpaired = proforma_seqs - invoice_seqs
        if unpaired:
            raise InvoiceStateMachineError(
                f"Proforma(s) #{', '.join(str(s) for s in sorted(unpaired))} not yet invoiced")

        if self.repo.get_invoice_by_anexa_and_type(anexa_id, InvoiceTypeEnum.STORNO):
            raise InvoiceStateMachineError("Storno already exists")

        # Verify full anexa amount is invoiced
        lines = self.repo.get_lines_by_anexa(anexa_id)
        anexa_total = sum(Decimal(str(l["selling_price_eur"])) for l in lines)
        invoiced_total = sum(Decimal(str(r["total_amount_eur"])) for r in invoices)
        if anexa_total > 0 and invoiced_total < anexa_total:
            remaining = anexa_total - invoiced_total
            raise InvoiceStateMachineError(
                f"Cannot issue Storno — only {invoiced_total} of {anexa_total} EUR invoiced. "
                f"Remaining {remaining} EUR must be invoiced first.")

        storno_total = sum(Decimal(str(r["total_amount_eur"])) for r in invoices)

        # Weighted average kurs
        weighted_sum = Decimal("0")
        amount_sum = Decimal("0")
        for inv in invoices:
            amt = Decimal(str(inv["total_amount_eur"]))
            k = Decimal(str(inv["kurs_applied"])) if inv.get("kurs_applied") else None
            if k and amt:
                weighted_sum += amt * k
                amount_sum += amt
        storno_kurs = (weighted_sum / amount_sum).quantize(Decimal("0.0001")) if amount_sum else None
        storno_ron = (storno_total * storno_kurs) if storno_kurs else Decimal("0")

        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.STORNO,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=1,
            total_amount_eur=-storno_total,
            total_amount_ron=-storno_ron,
            kurs_applied=storno_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes or f"Reverses {len(invoices)} invoice(s)",
            created_by=created_by_user_id,
        )

        for inv in invoices:
            self.repo.create_link(
                source_invoice_id=inv["id"],
                target_invoice_id=inv_row["id"],
                link_type=InvoiceLinkTypeEnum.REVERSES,
            )

        logger.info("Storno created: anexa=%s amount=%s EUR", anexa_id, -storno_total)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Final ──────────────────────────────────────────────

    def issue_final(self, anexa_id: int,
                    invoice_number: int | None = None, issued_date=None,
                    intocmit_de: str | None = None,
                    notes: str | None = None,
                    created_by_user_id: int = 0) -> StoredInvoice:
        """Issue the Final invoice after Storno."""
        storno_row = self.repo.get_invoice_by_anexa_and_type(anexa_id, InvoiceTypeEnum.STORNO)
        if not storno_row:
            raise InvoiceStateMachineError("Storno required before Final")
        if self.repo.get_invoice_by_anexa_and_type(anexa_id, InvoiceTypeEnum.FINAL):
            raise InvoiceStateMachineError("Final already exists")

        final_total = abs(Decimal(str(storno_row["total_amount_eur"])))
        storno_kurs = Decimal(str(storno_row["kurs_applied"])) if storno_row.get("kurs_applied") else None
        final_ron = (final_total * storno_kurs) if storno_kurs else Decimal("0")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.FINAL,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=1,
            total_amount_eur=final_total,
            total_amount_ron=final_ron,
            kurs_applied=storno_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes,
            created_by=created_by_user_id,
        )

        self.repo.create_link(
            source_invoice_id=storno_row["id"],
            target_invoice_id=inv_row["id"],
            link_type=InvoiceLinkTypeEnum.REPLACES,
        )

        logger.info("Final created: anexa=%s amount=%s EUR", anexa_id, final_total)
        return StoredInvoice.from_row(inv_row)

    # ── Query helpers ────────────────────────────────────────────

    def get_next_actions(self, anexa_id: int) -> list[str]:
        existing = self.repo.get_invoices_by_anexa(anexa_id)
        types = {}
        for row in existing:
            types.setdefault(row["invoice_type"], []).append(row)

        if "FINAL" in types:
            return []
        if "STORNO" in types:
            return ["FINAL"]

        actions = []
        proforma_seqs = {r["sequence_number"] for r in types.get("PROFORMA", [])}
        invoice_seqs = {r["sequence_number"] for r in types.get("INVOICE", [])}
        unpaired = proforma_seqs - invoice_seqs

        # Can add proforma only if all existing ones are invoiced AND remaining > 0
        if not unpaired:
            anexa_lines = self.repo.get_lines_by_anexa(anexa_id)
            anexa_total = sum(Decimal(str(l["selling_price_eur"])) for l in anexa_lines)
            proformas_total = sum(Decimal(str(r["total_amount_eur"])) for r in types.get("PROFORMA", []))
            if proformas_total < anexa_total:
                actions.append("PROFORMA")

        # Can issue invoice for unpaired proformas
        if unpaired:
            actions.append("INVOICE")

        # Can storno only if all proformas invoiced
        if proforma_seqs and proforma_seqs == invoice_seqs:
            actions.append("STORNO")

        return actions

    def get_unpaired_proformas(self, anexa_id: int) -> list[dict]:
        existing = self.repo.get_invoices_by_anexa(anexa_id)
        proformas = {r["sequence_number"]: r for r in existing if r["invoice_type"] == "PROFORMA"}
        invoiced = {r["sequence_number"] for r in existing if r["invoice_type"] == "INVOICE"}
        return [proformas[s] for s in sorted(proformas.keys() - invoiced)]
