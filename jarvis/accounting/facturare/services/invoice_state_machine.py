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

    def _check_invoice_number_unique(self, anexa_id: int, invoice_number: int | None, invoice_type: str | None = None):
        """Ensure invoice_number is not already used on this anexa for the same document type."""
        if invoice_number is None:
            return
        if invoice_type:
            existing = self.repo.query_all(
                "SELECT id, invoice_type, sequence_number FROM facturare_invoices "
                "WHERE anexa_id = %s AND invoice_number = %s AND invoice_type = %s",
                (anexa_id, invoice_number, invoice_type))
        else:
            existing = self.repo.query_all(
                "SELECT id, invoice_type, sequence_number FROM facturare_invoices "
                "WHERE anexa_id = %s AND invoice_number = %s",
                (anexa_id, invoice_number))
        if existing:
            row = existing[0]
            raise InvoiceStateMachineError(
                f"Invoice number {invoice_number} already used on this anexa "
                f"({row['invoice_type']} #{row['sequence_number']})")

    # ── Issue Proforma ───────────────────────────────────────────

    def issue_proforma(self, anexa_id: int, amount_eur: Decimal,
                       split_mode: str = "equal",
                       invoice_number: int | None = None, issued_date=None,
                       intocmit_de: str | None = None, notes: str | None = None,
                       line_ids: list[int] | None = None,
                       created_by_user_id: int = 0,
                       doc_mode: str = "per_car") -> StoredInvoice:
        """Issue a Proforma for an Anexa (optionally for selected lines only)."""
        # Check no STORNO yet
        existing_storno = self.repo.get_invoice_by_anexa_and_type(anexa_id, InvoiceTypeEnum.STORNO)
        if existing_storno:
            raise InvoiceStateMachineError("Cannot add proforma after STORNO")

        # Check amount doesn't exceed anexa total value
        anexa_lines = self.repo.get_lines_by_anexa(anexa_id)

        # If line_ids provided, validate they belong to this anexa
        if line_ids:
            valid_ids = {l["id"] for l in anexa_lines}
            invalid = set(line_ids) - valid_ids
            if invalid:
                raise InvoiceStateMachineError(f"Line IDs {invalid} not found in this anexa")

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

        # Proformas covering the SAME cars must be paired before issuing a new one
        import json as _json
        existing_invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)
        invoice_seqs = {i["sequence_number"] for i in existing_invoices}
        all_line_id_set = {l["id"] for l in anexa_lines}
        new_line_set = set(line_ids) if line_ids else all_line_id_set
        for p in existing_proformas:
            if p["sequence_number"] in invoice_seqs:
                continue  # already paired
            # Unpaired proforma — check if it overlaps with the new one
            raw = p.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            p_lines = set(raw) if raw else all_line_id_set
            overlap = new_line_set & p_lines
            if overlap:
                raise InvoiceStateMachineError(
                    f"Proforma #{p['sequence_number']} not yet invoiced — it covers some of the same vehicles")

        self._check_invoice_number_unique(anexa_id, invoice_number, "PROFORMA")
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
            line_ids=line_ids,
            doc_mode=doc_mode,
        )
        logger.info("Proforma #%d created: anexa=%s amount=%s EUR lines=%s mode=%s", seq, anexa_id, amount_eur, line_ids or "all", doc_mode)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Invoice ────────────────────────────────────────────

    def issue_invoice(self, anexa_id: int, sequence_number: int,
                      invoice_number: int | None = None, issued_date=None,
                      intocmit_de: str | None = None,
                      notes: str | None = None,
                      created_by_user_id: int = 0,
                      doc_mode: str | None = None) -> StoredInvoice:
        """Issue an Invoice confirming payment of a specific Proforma."""
        proforma_row = self.repo.get_invoice_by_anexa_type_and_seq(
            anexa_id, InvoiceTypeEnum.PROFORMA, sequence_number)
        if not proforma_row:
            raise InvoiceStateMachineError(f"Proforma #{sequence_number} not found")

        existing = self.repo.get_invoice_by_anexa_type_and_seq(
            anexa_id, InvoiceTypeEnum.INVOICE, sequence_number)
        if existing:
            raise InvoiceStateMachineError(f"Invoice #{sequence_number} already exists")

        self._check_invoice_number_unique(anexa_id, invoice_number, "INVOICE")
        proforma_amount = Decimal(str(proforma_row["total_amount_eur"]))
        proforma_kurs = Decimal(str(proforma_row["kurs_applied"])) if proforma_row.get("kurs_applied") else None
        total_ron = (proforma_amount * proforma_kurs) if proforma_kurs else Decimal("0")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        # Inherit line_ids from the proforma being confirmed
        import json as _json
        proforma_line_ids = proforma_row.get("line_ids")
        if isinstance(proforma_line_ids, str):
            proforma_line_ids = _json.loads(proforma_line_ids)

        effective_doc_mode = doc_mode or proforma_row.get("doc_mode", "per_car")
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
            line_ids=proforma_line_ids,
            doc_mode=effective_doc_mode,
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
                     line_ids: list[int] | None = None,
                     created_by_user_id: int = 0) -> StoredInvoice:
        """Issue a Storno reversing INVOICES for selected cars (or all if no line_ids)."""
        import json as _json

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        target_lines = set(line_ids) if line_ids else all_line_id_set

        if line_ids:
            invalid = target_lines - all_line_id_set
            if invalid:
                raise InvoiceStateMachineError(f"Line IDs {invalid} not found in this anexa")

        proformas = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.PROFORMA)
        invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)

        # Filter to invoices that cover the target cars
        def covers_target(inv):
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            inv_lines = set(raw) if raw else all_line_id_set
            return bool(inv_lines & target_lines)

        relevant_proformas = [p for p in proformas if covers_target(p)]
        relevant_invoices = [i for i in invoices if covers_target(i)]

        if not relevant_proformas:
            raise InvoiceStateMachineError("No proformas found for selected vehicles")

        # Check all relevant proformas are paired
        proforma_seqs = {r["sequence_number"] for r in relevant_proformas}
        invoice_seqs = {r["sequence_number"] for r in relevant_invoices}
        unpaired = proforma_seqs - invoice_seqs
        if unpaired:
            raise InvoiceStateMachineError(
                f"Proforma(s) #{', '.join(str(s) for s in sorted(unpaired))} not yet invoiced")

        # Verify selected cars are fully invoiced
        line_prices = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}
        target_total = sum(line_prices.get(lid, Decimal("0")) for lid in target_lines)
        # Sum proportional share of each invoice for the target cars
        invoiced_for_target = Decimal("0")
        for inv in relevant_invoices:
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            inv_lines = set(raw) if raw else all_line_id_set
            covered_total = sum(line_prices.get(lid, Decimal("0")) for lid in inv_lines)
            for lid in (inv_lines & target_lines):
                share = (line_prices.get(lid, Decimal("0")) / covered_total * Decimal(str(inv["total_amount_eur"]))) if covered_total else Decimal("0")
                invoiced_for_target += share

        if target_total > 0 and invoiced_for_target < target_total * Decimal("0.999"):
            remaining = target_total - invoiced_for_target
            raise InvoiceStateMachineError(
                f"Cannot issue Storno — only {invoiced_for_target:.2f} of {target_total:.2f} EUR invoiced "
                f"for selected vehicles. Remaining {remaining:.2f} EUR must be invoiced first.")

        storno_total = invoiced_for_target

        # Weighted average kurs from relevant invoices
        weighted_sum = Decimal("0")
        amount_sum = Decimal("0")
        for inv in relevant_invoices:
            amt = Decimal(str(inv["total_amount_eur"]))
            k = Decimal(str(inv["kurs_applied"])) if inv.get("kurs_applied") else None
            if k and amt:
                weighted_sum += amt * k
                amount_sum += amt
        storno_kurs = (weighted_sum / amount_sum).quantize(Decimal("0.0001")) if amount_sum else None
        storno_ron = (storno_total * storno_kurs) if storno_kurs else Decimal("0")

        self._check_invoice_number_unique(anexa_id, invoice_number, "STORNO")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)
        existing_stornos = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.STORNO)
        seq = len(existing_stornos) + 1

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.STORNO,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=seq,
            total_amount_eur=-storno_total,
            total_amount_ron=-storno_ron,
            kurs_applied=storno_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes or f"Reverses invoices for {len(target_lines)} vehicle(s)",
            created_by=created_by_user_id,
            line_ids=list(target_lines) if line_ids else None,
        )

        for inv in relevant_invoices:
            self.repo.create_link(
                source_invoice_id=inv["id"],
                target_invoice_id=inv_row["id"],
                link_type=InvoiceLinkTypeEnum.REVERSES,
            )

        logger.info("Storno #%d created: anexa=%s amount=%s EUR lines=%s", seq, anexa_id, -storno_total, line_ids or "all")
        return StoredInvoice.from_row(inv_row)

    # ── Issue Final ──────────────────────────────────────────────

    def issue_final(self, anexa_id: int,
                    invoice_number: int | None = None, issued_date=None,
                    intocmit_de: str | None = None,
                    notes: str | None = None,
                    line_ids: list[int] | None = None,
                    created_by_user_id: int = 0) -> StoredInvoice:
        """Issue the Final invoice after Storno (for selected cars or all)."""
        import json as _json

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        target_lines = set(line_ids) if line_ids else all_line_id_set

        # Find storno(s) covering the target cars
        stornos = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.STORNO)
        matching_storno = None
        for s in stornos:
            raw = s.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            s_lines = set(raw) if raw else all_line_id_set
            if target_lines <= s_lines:
                matching_storno = s
                break
        if not matching_storno:
            raise InvoiceStateMachineError("Storno required before Final for the selected vehicles")

        # Compute final amount as proportional share of the storno for target cars
        line_prices = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}
        raw = matching_storno.get("line_ids")
        if isinstance(raw, str):
            raw = _json.loads(raw)
        storno_lines = set(raw) if raw else all_line_id_set
        storno_lines_total = sum(line_prices.get(lid, Decimal("0")) for lid in storno_lines)
        target_total = sum(line_prices.get(lid, Decimal("0")) for lid in target_lines)
        storno_amount = abs(Decimal(str(matching_storno["total_amount_eur"])))
        final_total = (target_total / storno_lines_total * storno_amount) if storno_lines_total else storno_amount

        # Weighted average kurs from all prior invoices covering target cars
        all_invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)
        sum_eur_x_kurs = Decimal("0")
        sum_eur = Decimal("0")
        for inv in all_invoices:
            inv_kurs = Decimal(str(inv["kurs_applied"])) if inv.get("kurs_applied") else None
            if not inv_kurs:
                continue
            inv_raw = inv.get("line_ids")
            if isinstance(inv_raw, str):
                inv_raw = _json.loads(inv_raw)
            inv_lids = set(inv_raw) if inv_raw else all_line_id_set
            overlap = target_lines & inv_lids
            if not overlap:
                continue
            inv_total = Decimal(str(inv["total_amount_eur"]))
            inv_covered_total = sum(line_prices.get(lid, Decimal("0")) for lid in inv_lids)
            for lid in overlap:
                share = (line_prices.get(lid, Decimal("0")) / inv_covered_total * inv_total) if inv_covered_total else Decimal("0")
                sum_eur_x_kurs += share * inv_kurs
                sum_eur += share
        final_kurs = (sum_eur_x_kurs / sum_eur).quantize(Decimal("0.0001")) if sum_eur else None
        final_ron = (final_total * final_kurs) if final_kurs else Decimal("0")
        self._check_invoice_number_unique(anexa_id, invoice_number, "FINAL")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)
        existing_finals = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.FINAL)
        seq = len(existing_finals) + 1

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.FINAL,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=seq,
            total_amount_eur=final_total,
            total_amount_ron=final_ron,
            kurs_applied=final_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes,
            created_by=created_by_user_id,
            line_ids=list(target_lines) if line_ids else None,
        )

        self.repo.create_link(
            source_invoice_id=matching_storno["id"],
            target_invoice_id=inv_row["id"],
            link_type=InvoiceLinkTypeEnum.REPLACES,
        )

        logger.info("Final #%d created: anexa=%s amount=%s EUR lines=%s", seq, anexa_id, final_total, line_ids or "all")
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
