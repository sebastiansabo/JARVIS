"""Invoice State Machine — enforces the paired PROFORMA/INVOICE lifecycle per Anexa.

    PROFORMA 1 → INVOICE 1 (after payment)
    PROFORMA N → INVOICE N (after payment)
    STORNO (reverses all INVOICES)
    FINAL (full amount)

Entity hierarchy: Contract → Anexa → Invoices.
Vehicle lines live on the Anexa, not on invoices.
"""
import json as _json
import logging
from decimal import Decimal, ROUND_HALF_UP

import psycopg2.errors

ONE = Decimal("1")

from ..models import StoredInvoice, InvoiceTypeEnum, InvoiceStateEnum, InvoiceLinkTypeEnum
from ..repositories.invoice_storage_repository import InvoiceStorageRepository
from .document_numbering import allocate
from .advance_alloc import partial_advance_total, WHOLE_EUR, CENTS

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

    def _coerce_kurs(self, value) -> Decimal | None:
        """Normalise a user-supplied manual kurs override to 4 decimals.

        BNR now bot-blocks programmatic access to its rate XML (it 302-redirects
        the file to its homepage), so the auto-fetch can silently fail. Letting
        the user type the official rate keeps invoicing unblocked. Blank, zero,
        and non-numeric input all resolve to None so the normal auto-fetch path
        still runs."""
        if value in (None, ""):
            return None
        try:
            k = Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except (ArithmeticError, ValueError, TypeError):
            return None
        return k if k > 0 else None

    def _require_kurs(self, kurs, issued_date, doc_label: str):
        """Refuse to issue a foreign-currency document without a BNR exchange rate.

        Romanian invoicing requires the BNR rate on EUR documents, and downstream
        consumers (storno per-line Kurs, FINAL weighted average, EuroFib export)
        all depend on it. Silently storing NULL is exactly what hid the missing-Kurs
        bug, so fail loudly and actionably instead of producing a defective invoice."""
        if kurs:
            return
        raise InvoiceStateMachineError(
            f"Could not determine the BNR exchange rate for {doc_label} "
            f"(issued {issued_date or 'without a date'}). The rate service may be "
            f"temporarily unavailable — set the issue date and retry in a moment."
        )

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

    def _supplier_id_for_anexa(self, anexa_id: int) -> int:
        anexa = self.repo.get_anexa_by_id(anexa_id)
        contract = self.repo.get_contract_by_id(anexa["contract_id"])
        return contract["supplier_id"]

    def _ordered_line_ids(self, inv_row: dict, anexa_id: int) -> list[int]:
        """Return the line_ids in the exact order they were stored on inv_row.

        Falls back to all anexa lines (in line_number order) when the invoice
        covers the whole anexa (line_ids is None) — this matches the order
        every other consumer (PDF/eurofib/backfill) uses in that case.
        """
        raw = inv_row.get("line_ids")
        if isinstance(raw, str):
            raw = _json.loads(raw)
        if raw:
            return list(raw)
        return [l["id"] for l in self.repo.get_lines_by_anexa(anexa_id)]

    def _persist_document_numbers(self, inv_row: dict, anexa_id: int) -> None:
        """Allocate + store per-document numbers for a just-created invoice row.

        Ordering/doc_mode are derived from what create_invoice actually STORED
        on inv_row (not from method-local variables) so that Task 6/7 consumers
        and the Task 5 backfill — which map position -> car from the stored
        line_ids — stay consistent with what's persisted here.
        """
        supplier_id = self._supplier_id_for_anexa(anexa_id)
        ordered = self._ordered_line_ids(inv_row, anexa_id)
        rows = allocate(inv_row["invoice_type"], inv_row.get("invoice_number"),
                        inv_row.get("doc_mode", "per_car"), ordered)
        try:
            self.repo.replace_document_numbers(inv_row["id"], supplier_id, rows)
        except psycopg2.errors.ExclusionViolation:
            # This invoice's number is already owned by a DIFFERENT invoice of
            # the same supplier+series (excl_facturare_docnum_cross_invoice).
            # create_invoice() already committed the invoice row above, so we
            # must delete it here — otherwise it's left committed with no
            # document-number rows and a retry would create a duplicate
            # invoice. The FK from facturare_document_numbers and
            # facturare_invoice_links is ON DELETE CASCADE, so this single
            # delete cleans up everything for this invoice.
            self.repo.delete_invoice(inv_row["id"])
            raise InvoiceStateMachineError(
                f"Invoice number {inv_row.get('invoice_number')} is already "
                f"used by another invoice for this supplier")

    # ── Issue Proforma ───────────────────────────────────────────

    def issue_proforma(self, anexa_id: int, amount_eur: Decimal,
                       split_mode: str = "equal",
                       invoice_number: int | None = None, issued_date=None,
                       intocmit_de: str | None = None, notes: str | None = None,
                       line_ids: list[int] | None = None,
                       created_by_user_id: int = 0,
                       doc_mode: str = "per_car",
                       round_decimals: bool = False) -> StoredInvoice:
        """Issue a Proforma for an Anexa (optionally for selected lines only)."""
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
        # Stornos free up capacity — add back stornoed amounts
        existing_stornos = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.STORNO)
        storno_freed = sum(abs(Decimal(str(s["total_amount_eur"]))) for s in existing_stornos)
        remaining = anexa_total - proformas_total + storno_freed

        if remaining <= 0:
            raise InvoiceStateMachineError(
                f"Anexa fully covered by existing proformas ({proformas_total} / {anexa_total} EUR)")

        if amount_eur > remaining:
            raise InvoiceStateMachineError(
                f"Amount {amount_eur} EUR exceeds remaining {remaining} EUR "
                f"(anexa: {anexa_total}, proformas: {proformas_total})")

        # A car may sit on only ONE proforma that still has uninvoiced lines.
        # Block a new proforma overlapping lines still OPEN on an existing one
        # (line-based: a partially-invoiced proforma still guards its rest).
        import json as _json
        all_line_id_set = {l["id"] for l in anexa_lines}
        new_line_set = set(line_ids) if line_ids else all_line_id_set
        invoiced_by_seq = self._invoiced_lines_by_seq(
            self.repo.get_invoices_by_anexa(anexa_id), all_line_id_set)
        for p in existing_proformas:
            raw = p.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            p_lines = set(raw) if raw else all_line_id_set
            open_lines = p_lines - invoiced_by_seq.get(p["sequence_number"], set())
            overlap = new_line_set & open_lines
            if overlap:
                raise InvoiceStateMachineError(
                    f"Proforma #{p['sequence_number']} not yet invoiced — it covers some of the same vehicles")

        self._check_invoice_number_unique(anexa_id, invoice_number, "PROFORMA")
        seq = len(existing_proformas) + 1
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.PROFORMA,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=seq,
            total_amount_eur=amount_eur,
            total_amount_ron=Decimal("0"),
            kurs_applied=None,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            split_mode=split_mode,
            notes=notes,
            created_by=created_by_user_id,
            line_ids=line_ids,
            doc_mode=doc_mode,
            round_decimals=round_decimals,
        )
        logger.info("Proforma #%d created: anexa=%s amount=%s EUR lines=%s mode=%s decimals=%s", seq, anexa_id, amount_eur, line_ids or "all", doc_mode, round_decimals)
        self._persist_document_numbers(inv_row, anexa_id)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Invoice ────────────────────────────────────────────

    def issue_invoice(self, anexa_id: int, sequence_number: int,
                      invoice_number: int | None = None, issued_date=None,
                      intocmit_de: str | None = None,
                      notes: str | None = None,
                      created_by_user_id: int = 0,
                      doc_mode: str | None = None,
                      manual_kurs=None,
                      round_decimals: bool | None = None,
                      line_ids: list[int] | None = None) -> StoredInvoice:
        """Issue an advance invoice (factură de avans) confirming payment of a Proforma.

        A single proforma covering N cars may be confirmed by MULTIPLE advance
        invoices, each over a disjoint subset of its lines (``line_ids``) — this
        lets accounting invoice only the cars that were actually paid (e.g. 5 of 7)
        and confirm the rest later. Passing ``line_ids=None`` confirms every line
        of the proforma still left uninvoiced (the whole proforma when untouched,
        so the pre-partial behaviour is preserved).

        Each partial books its cars at their canonical per-car advance slice; the
        invoice that *closes* the proforma books the residual so the partials
        reconcile to the proforma total exactly.

        A manual_kurs override (when the BNR rate service is unreachable) takes
        precedence over the auto-fetched rate so issuing never depends on BNR."""
        import json as _json
        proforma_row = self.repo.get_invoice_by_anexa_type_and_seq(
            anexa_id, InvoiceTypeEnum.PROFORMA, sequence_number)
        if not proforma_row:
            raise InvoiceStateMachineError(f"Proforma #{sequence_number} not found")

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        line_price = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}
        line_number_order = {l["id"]: l["line_number"] for l in all_lines}

        # Lines this proforma covers (None stored == whole anexa).
        p_raw = proforma_row.get("line_ids")
        if isinstance(p_raw, str):
            p_raw = _json.loads(p_raw)
        proforma_lines = set(p_raw) if p_raw else set(all_line_id_set)

        # Lines of this proforma already confirmed by earlier advance invoices.
        already = self._invoiced_lines_for_proforma(anexa_id, sequence_number, all_line_id_set)
        already_total = self._invoiced_total_for_proforma(anexa_id, sequence_number)
        remaining = proforma_lines - already
        if not remaining:
            raise InvoiceStateMachineError(
                f"Proforma #{sequence_number} is already fully invoiced")

        # Resolve which lines this invoice confirms.
        if line_ids:
            target = set(line_ids)
            outside = target - proforma_lines
            if outside:
                raise InvoiceStateMachineError(
                    f"Line IDs {sorted(outside)} are not part of proforma #{sequence_number}")
            dupes = target & already
            if dupes:
                raise InvoiceStateMachineError(
                    f"Line IDs {sorted(dupes)} are already invoiced under proforma #{sequence_number}")
        else:
            target = set(remaining)  # confirm everything still open on this proforma

        self._check_invoice_number_unique(anexa_id, invoice_number, "INVOICE")

        proforma_amount = Decimal(str(proforma_row["total_amount_eur"]))
        split_mode = proforma_row.get("split_mode", "equal")
        effective_round = round_decimals if round_decimals is not None else bool(proforma_row.get("round_decimals"))
        quant = CENTS if effective_round else WHOLE_EUR
        amount = partial_advance_total(
            proforma_amount, split_mode, quant,
            {lid: line_price[lid] for lid in proforma_lines},
            target, already, already_total)

        manual = self._coerce_kurs(manual_kurs)
        proforma_kurs = Decimal(str(proforma_row["kurs_applied"])) if proforma_row.get("kurs_applied") else None
        if manual:
            proforma_kurs = manual
        elif not proforma_kurs:
            proforma_kurs = self._fetch_kurs(issued_date)
        self._require_kurs(proforma_kurs, issued_date, f"Invoice #{sequence_number}")
        total_ron = (amount * proforma_kurs) if proforma_kurs else Decimal("0")
        intocmit = self._resolve_intocmit(intocmit_de, created_by_user_id)

        # Store None only when this invoice covers the WHOLE anexa (preserves the
        # existing "line_ids null == all lines" convention every consumer relies on);
        # otherwise store the explicit subset in line_number order.
        sorted_target = sorted(target, key=lambda lid: line_number_order.get(lid, lid))
        store_line_ids = None if target == all_line_id_set else sorted_target

        effective_doc_mode = doc_mode if doc_mode else proforma_row.get("doc_mode", "per_car")
        inv_row = self.repo.create_invoice(
            anexa_id=anexa_id,
            invoice_type=InvoiceTypeEnum.INVOICE,
            invoice_state=InvoiceStateEnum.DRAFT,
            sequence_number=sequence_number,
            total_amount_eur=amount,
            total_amount_ron=total_ron,
            kurs_applied=proforma_kurs,
            invoice_number=invoice_number,
            issued_date=issued_date,
            intocmit_de=intocmit,
            notes=notes or f"Confirms Proforma #{sequence_number} (No: {proforma_row.get('invoice_number') or 'N/A'})",
            split_mode=split_mode,
            created_by=created_by_user_id,
            line_ids=store_line_ids,
            doc_mode=effective_doc_mode,
            round_decimals=effective_round,
        )

        self.repo.create_link(
            source_invoice_id=proforma_row["id"],
            target_invoice_id=inv_row["id"],
            link_type=InvoiceLinkTypeEnum.PRECEDES,
        )

        logger.info("Invoice #%d created: anexa=%s amount=%s EUR lines=%s", sequence_number, anexa_id, amount, store_line_ids or "all")
        self._persist_document_numbers(inv_row, anexa_id)
        return StoredInvoice.from_row(inv_row)

    def _invoiced_lines_for_proforma(self, anexa_id: int, proforma_seq: int,
                                     all_line_id_set: set) -> set:
        """Lines already confirmed by advance invoices belonging to a proforma.

        An advance invoice belongs to its proforma via the shared sequence_number
        (INVOICE #N confirms PROFORMA #N). Multiple partial invoices may share
        that sequence, each over a disjoint line subset."""
        import json as _json
        covered = set()
        for inv in self.repo.get_invoices_by_anexa(anexa_id):
            if inv["invoice_type"] != "INVOICE" or inv["sequence_number"] != proforma_seq:
                continue
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            covered |= set(raw) if raw else set(all_line_id_set)
        return covered

    def _invoiced_total_for_proforma(self, anexa_id: int, proforma_seq: int) -> Decimal:
        """Sum of the totals of advance invoices already issued for a proforma."""
        total = Decimal("0")
        for inv in self.repo.get_invoices_by_anexa(anexa_id):
            if inv["invoice_type"] == "INVOICE" and inv["sequence_number"] == proforma_seq:
                total += Decimal(str(inv["total_amount_eur"]))
        return total

    # ── Issue Storno ─────────────────────────────────────────────

    def issue_storno(self, anexa_id: int,
                     invoice_number: int | None = None, issued_date=None,
                     intocmit_de: str | None = None,
                     notes: str | None = None,
                     line_ids: list[int] | None = None,
                     target_invoice_ids: list[int] | None = None,
                     created_by_user_id: int = 0,
                     manual_kurs=None,
                     round_decimals: bool | None = None) -> StoredInvoice:
        """Issue a Storno reversing INVOICES for selected cars (or all if no line_ids)."""
        import json as _json

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        target_lines = set(line_ids) if line_ids else all_line_id_set

        if line_ids:
            invalid = target_lines - all_line_id_set
            if invalid:
                raise InvoiceStateMachineError(f"Line IDs {invalid} not found in this anexa")

        # Preserve line_number ordering for deterministic per-car invoice numbering
        line_number_order = {l["id"]: l["line_number"] for l in all_lines}
        sorted_target_line_ids = sorted(target_lines, key=lambda lid: line_number_order.get(lid, lid))

        proformas = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.PROFORMA)
        invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)

        # Filter to invoices that cover the target cars
        def covers_target(inv):
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            inv_lines = set(raw) if raw else all_line_id_set
            return bool(inv_lines & target_lines)

        # Filter to specific target invoices if provided, otherwise all covering target cars
        if target_invoice_ids:
            target_inv_set = set(target_invoice_ids)
            relevant_invoices = [i for i in invoices if i["id"] in target_inv_set]
        else:
            relevant_invoices = [i for i in invoices if covers_target(i)]

        if not relevant_invoices:
            raise InvoiceStateMachineError("No invoices found for selected vehicles")

        # Reverse in the same rounding mode the invoices were booked in, so the
        # storno total nets them to zero (explicit override wins, else inherit).
        effective_round = round_decimals if round_decimals is not None else any(
            inv.get("round_decimals") for inv in relevant_invoices)
        share_q = Decimal("0.01") if effective_round else ONE

        # Sum proportional share of each invoice for the target cars
        line_prices = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}
        invoiced_for_target = Decimal("0")
        for inv in relevant_invoices:
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            inv_lines = set(raw) if raw else all_line_id_set
            covered_total = sum(line_prices.get(lid, Decimal("0")) for lid in inv_lines)
            for lid in (inv_lines & target_lines):
                share = (line_prices.get(lid, Decimal("0")) / covered_total * Decimal(str(inv["total_amount_eur"]))).quantize(share_q, rounding=ROUND_HALF_UP) if covered_total else Decimal("0")
                invoiced_for_target += share

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
        if not storno_kurs:
            storno_kurs = self._coerce_kurs(manual_kurs) or self._fetch_kurs(issued_date)
        self._require_kurs(storno_kurs, issued_date, "Storno")
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
            line_ids=sorted_target_line_ids if line_ids else None,
            round_decimals=effective_round,
        )

        for inv in relevant_invoices:
            self.repo.create_link(
                source_invoice_id=inv["id"],
                target_invoice_id=inv_row["id"],
                link_type=InvoiceLinkTypeEnum.REVERSES,
            )

        logger.info("Storno #%d created: anexa=%s amount=%s EUR lines=%s", seq, anexa_id, -storno_total, line_ids or "all")
        self._persist_document_numbers(inv_row, anexa_id)
        return StoredInvoice.from_row(inv_row)

    # ── Issue Final ──────────────────────────────────────────────

    def issue_final(self, anexa_id: int,
                    invoice_number: int | None = None, issued_date=None,
                    intocmit_de: str | None = None,
                    notes: str | None = None,
                    line_ids: list[int] | None = None,
                    created_by_user_id: int = 0,
                    manual_kurs=None,
                    round_decimals: bool | None = None) -> StoredInvoice:
        """Issue the Final invoice after Storno (for selected cars or all)."""
        import json as _json

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        target_lines = set(line_ids) if line_ids else all_line_id_set

        # Preserve line_number ordering for deterministic per-car invoice numbering
        line_number_order = {l["id"]: l["line_number"] for l in all_lines}
        sorted_target_line_ids = sorted(target_lines, key=lambda lid: line_number_order.get(lid, lid))

        # Verify at least one storno covers the target cars
        stornos = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.STORNO)
        matching_storno = None
        for s in stornos:
            raw = s.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            s_lines = set(raw) if raw else all_line_id_set
            if target_lines & s_lines:
                matching_storno = s
                break
        if not matching_storno:
            raise InvoiceStateMachineError("Storno required before Final for the selected vehicles")

        # Final is for the amount left to invoice (selling price - net invoiced after stornos)
        line_prices = {l["id"]: Decimal(str(l["selling_price_eur"])) for l in all_lines}
        target_total = sum(line_prices.get(lid, Decimal("0")) for lid in target_lines)

        # Compute net invoiced per target car: invoices minus stornos
        all_invoices = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.INVOICE)
        all_stornos = self.repo.get_invoices_by_anexa_and_type_list(anexa_id, InvoiceTypeEnum.STORNO)
        # Net in the same rounding mode the prior invoices/stornos used, so the
        # residual (final total) matches what those documents actually booked.
        effective_round = round_decimals if round_decimals is not None else any(
            inv.get("round_decimals") for inv in all_invoices)
        share_q = Decimal("0.01") if effective_round else ONE
        net_invoiced = Decimal("0")
        for inv in all_invoices:
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            inv_lines = set(raw) if raw else all_line_id_set
            covered_total = sum(line_prices.get(lid, Decimal("0")) for lid in inv_lines)
            for lid in (inv_lines & target_lines):
                share = (line_prices.get(lid, Decimal("0")) / covered_total * Decimal(str(inv["total_amount_eur"]))).quantize(share_q, rounding=ROUND_HALF_UP) if covered_total else Decimal("0")
                net_invoiced += share
        for s in all_stornos:
            raw = s.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            s_lines = set(raw) if raw else all_line_id_set
            covered_total = sum(line_prices.get(lid, Decimal("0")) for lid in s_lines)
            for lid in (s_lines & target_lines):
                share = (line_prices.get(lid, Decimal("0")) / covered_total * abs(Decimal(str(s["total_amount_eur"])))).quantize(share_q, rounding=ROUND_HALF_UP) if covered_total else Decimal("0")
                net_invoiced -= share
        final_total = target_total - net_invoiced

        # Weighted average kurs from all prior invoices covering target cars
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
                share = (line_prices.get(lid, Decimal("0")) / inv_covered_total * inv_total).quantize(ONE, rounding=ROUND_HALF_UP) if inv_covered_total else Decimal("0")
                sum_eur_x_kurs += share * inv_kurs
                sum_eur += share
        final_kurs = (sum_eur_x_kurs / sum_eur).quantize(Decimal("0.0001")) if sum_eur else None
        if not final_kurs:
            final_kurs = self._coerce_kurs(manual_kurs) or self._fetch_kurs(issued_date)
        self._require_kurs(final_kurs, issued_date, "Final invoice")
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
            line_ids=sorted_target_line_ids if line_ids else None,
            split_mode="proportional",
            round_decimals=effective_round,
        )

        self.repo.create_link(
            source_invoice_id=matching_storno["id"],
            target_invoice_id=inv_row["id"],
            link_type=InvoiceLinkTypeEnum.REPLACES,
        )

        logger.info("Final #%d created: anexa=%s amount=%s EUR lines=%s", seq, anexa_id, final_total, line_ids or "all")
        self._persist_document_numbers(inv_row, anexa_id)
        return StoredInvoice.from_row(inv_row)

    # ── Query helpers ────────────────────────────────────────────

    def _invoiced_lines_by_seq(self, existing: list, all_line_id_set: set) -> dict:
        """{proforma_seq: set(lines already confirmed)} — advance invoices share
        their proforma's sequence_number, each covering a disjoint line subset."""
        import json as _json
        out: dict = {}
        for inv in existing:
            if inv["invoice_type"] != "INVOICE":
                continue
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            cov = set(raw) if raw else set(all_line_id_set)
            out.setdefault(inv["sequence_number"], set()).update(cov)
        return out

    def get_next_actions(self, anexa_id: int) -> list[str]:
        import json as _json
        existing = self.repo.get_invoices_by_anexa(anexa_id)
        types = {}
        for row in existing:
            types.setdefault(row["invoice_type"], []).append(row)
        if "FINAL" in types:
            return []

        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}

        def _cov(inv):
            raw = inv.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            return set(raw) if raw else set(all_line_id_set)

        invoiced_by_seq = self._invoiced_lines_by_seq(existing, all_line_id_set)

        # Proforma lines still awaiting an advance invoice (line-based so a
        # partially-invoiced proforma still offers INVOICE for its rest).
        proforma_open_lines = set()
        for p in types.get("PROFORMA", []):
            proforma_open_lines |= (_cov(p) - invoiced_by_seq.get(p["sequence_number"], set()))

        actions = []
        anexa_total = sum(Decimal(str(l["selling_price_eur"])) for l in all_lines)
        proformas_total = sum(Decimal(str(r["total_amount_eur"])) for r in types.get("PROFORMA", []))
        storno_freed = sum(abs(Decimal(str(r["total_amount_eur"]))) for r in types.get("STORNO", []))
        if proformas_total - storno_freed < anexa_total:
            actions.append("PROFORMA")
        if proforma_open_lines:
            actions.append("INVOICE")

        # Storno reverses advance invoices; available while any invoiced line is
        # not yet stornoed.
        invoiced_lines = set().union(*invoiced_by_seq.values()) if invoiced_by_seq else set()
        stornoed_lines = set()
        for s in types.get("STORNO", []):
            stornoed_lines |= _cov(s)
        if invoiced_lines - stornoed_lines:
            actions.append("STORNO")

        # After a storno, the final invoice can be issued.
        if types.get("STORNO") and "FINAL" not in actions:
            actions.append("FINAL")

        return actions

    def get_unpaired_proformas(self, anexa_id: int) -> list[dict]:
        """Proformas with at least one line not yet confirmed by an advance invoice.

        Each returned row carries ``remaining_line_ids`` — the proforma's lines
        still open — so the UI can offer per-car selection when only part of a
        proforma has been paid."""
        import json as _json
        existing = self.repo.get_invoices_by_anexa(anexa_id)
        all_lines = self.repo.get_lines_by_anexa(anexa_id)
        all_line_id_set = {l["id"] for l in all_lines}
        line_number_order = {l["id"]: l["line_number"] for l in all_lines}
        invoiced_by_seq = self._invoiced_lines_by_seq(existing, all_line_id_set)

        out = []
        proformas = [r for r in existing if r["invoice_type"] == "PROFORMA"]
        for p in sorted(proformas, key=lambda r: r["sequence_number"]):
            raw = p.get("line_ids")
            if isinstance(raw, str):
                raw = _json.loads(raw)
            p_lines = set(raw) if raw else set(all_line_id_set)
            remaining = p_lines - invoiced_by_seq.get(p["sequence_number"], set())
            if remaining:
                d = dict(p)
                d["remaining_line_ids"] = sorted(
                    remaining, key=lambda lid: line_number_order.get(lid, lid))
                out.append(d)
        return out
