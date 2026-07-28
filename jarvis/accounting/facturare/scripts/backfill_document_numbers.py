"""Backfill `facturare_document_numbers` for every pre-existing invoice.

SAFETY-CRITICAL: this must reproduce, byte-for-byte, the per-document (per-car)
numbers each invoice was actually issued with. It does this by re-deriving the
ordering/doc_mode from the invoice's OWN stored `line_ids`/`doc_mode` using the
exact same helper the state machine uses at issue time
(`InvoiceStateMachine._ordered_line_ids` / `_supplier_id_for_anexa`), then
feeding that through the same `allocate()` function that produced the numbers
originally (see `services/document_numbering.py`). It never reads or writes
`invoice_number`, `doc_mode`, or `line_ids` on `facturare_invoices` itself —
those columns are the frozen historical record; this only populates the new
per-document registry table.

Safety properties:
  * Base preservation: for every invoice, the position-0 allocated number MUST
    equal the invoice's own `invoice_number`. If ANY invoice fails this check,
    the whole run refuses to write anything (see `base_mismatches`).
  * Collisions are not crashes: the `excl_facturare_docnum_cross_invoice`
    constraint may reject a number already owned by a DIFFERENT invoice (two
    historical invoices that happen to share a number). Each invoice is
    written in its own transaction (via `replace_document_numbers`, which
    commits/rolls back independently per call); a rejected invoice is skipped,
    recorded in `collisions`, and the run continues.
  * Idempotent: `replace_document_numbers` deletes-then-inserts per invoice,
    so re-running the backfill (e.g. after fixing a collision) does not
    duplicate rows.

Usage:
    python3 -m accounting.facturare.scripts.backfill_document_numbers          # dry run (default)
    python3 -m accounting.facturare.scripts.backfill_document_numbers --apply  # writes for real
"""
import argparse
import json
import logging

import psycopg2
import psycopg2.errors

from ..repositories.invoice_storage_repository import InvoiceStorageRepository
from ..services.document_numbering import allocate
from ..services.invoice_state_machine import InvoiceStateMachine

logger = logging.getLogger("jarvis.facturare.backfill_document_numbers")

_COLLISION_ERRORS = (psycopg2.errors.ExclusionViolation,)


class _LineCachingRepo:
    """Proxy that memoizes `get_lines_by_anexa()` per anexa_id.

    Many invoices share the same anexa (proforma/invoice/storno/final all
    reference the same vehicle lines), so without this the backfill would
    re-query the anexa's lines once per invoice instead of once per anexa.
    Everything else is delegated straight to the wrapped repo unchanged.
    """

    def __init__(self, repo):
        self._repo = repo
        self._cache = {}

    def get_lines_by_anexa(self, anexa_id):
        if anexa_id not in self._cache:
            self._cache[anexa_id] = self._repo.get_lines_by_anexa(anexa_id)
        return self._cache[anexa_id]

    def __getattr__(self, name):
        return getattr(self._repo, name)


def _find_conflicting_owner(repo, invoice_id, supplier_id, rows):
    """After a real EXCLUDE-constraint rejection, look up which OTHER invoice
    currently owns one of this invoice's candidate numbers (for reporting)."""
    for r in rows:
        if r["document_number"] is None:
            continue
        existing = repo.query_one(
            "SELECT invoice_id FROM facturare_document_numbers "
            "WHERE supplier_id=%s AND series=%s AND document_number=%s AND invoice_id <> %s "
            "LIMIT 1",
            (supplier_id, r["series"], r["document_number"], invoice_id))
        if existing:
            return {"series": r["series"], "document_number": r["document_number"],
                    "other_invoice_id": existing["invoice_id"]}
    return None


def backfill(repo=None, apply: bool = False) -> dict:
    """Backfill `facturare_document_numbers` for every row in `facturare_invoices`.

    Returns:
        {
            "invoices": int,           # total invoices scanned
            "rows_written": int,       # docnum rows actually (or, in dry-run,
                                        # would-be) persisted
            "base_mismatches": [...],  # non-empty => nothing was written, fix first
            "collisions": [...],       # invoices whose numbers collide with a
                                        # DIFFERENT invoice; not written, run continued
            "skipped": [...],          # invoices that couldn't be resolved at all
        }
    """
    repo = repo or InvoiceStorageRepository()
    sm = InvoiceStateMachine(repo=_LineCachingRepo(repo))
    supplier_cache: dict[int, int] = {}

    invoices = repo.query_all(
        "SELECT id, invoice_type, invoice_number, doc_mode, line_ids, anexa_id "
        "FROM facturare_invoices ORDER BY id")

    base_mismatches = []
    skipped = []
    plan = []  # [{invoice_id, supplier_id, rows}]

    for inv in invoices:
        invoice_id = inv["id"]
        anexa_id = inv["anexa_id"]

        try:
            ordered = sm._ordered_line_ids(inv, anexa_id)
        except Exception as e:
            skipped.append({"invoice_id": invoice_id, "reason": f"line resolution failed: {e}"})
            continue

        if not ordered:
            skipped.append({"invoice_id": invoice_id, "reason": "anexa has no resolvable lines"})
            continue

        if anexa_id not in supplier_cache:
            try:
                supplier_cache[anexa_id] = sm._supplier_id_for_anexa(anexa_id)
            except Exception as e:
                skipped.append({"invoice_id": invoice_id, "reason": f"supplier resolution failed: {e}"})
                continue
        supplier_id = supplier_cache[anexa_id]

        doc_mode = inv.get("doc_mode") or "per_car"
        rows = allocate(inv["invoice_type"], inv.get("invoice_number"), doc_mode, ordered)

        expected = inv.get("invoice_number")
        got = rows[0]["document_number"] if rows else None
        if got != expected:
            base_mismatches.append({"invoice_id": invoice_id, "expected": expected, "got": got})
            continue

        plan.append({"invoice_id": invoice_id, "supplier_id": supplier_id, "rows": rows})

    if base_mismatches:
        logger.error("Refusing to write: %d base_mismatches found", len(base_mismatches))
        return {
            "invoices": len(invoices),
            "rows_written": 0,
            "base_mismatches": base_mismatches,
            "collisions": [],
            "skipped": skipped,
        }

    collisions = []
    rows_written = 0

    if apply:
        # The database's EXCLUDE constraint is the single source of truth for
        # collisions here: each invoice gets its OWN delete-then-insert
        # transaction (`replace_document_numbers`, via `execute_many`, commits
        # or rolls back independently per call). The first invoice (in id
        # order) to claim a number wins; a later invoice reusing it gets a
        # genuine ExclusionViolation, which is caught — that invoice's write
        # is fully rolled back, it's recorded as a collision, and the loop
        # continues with the next invoice untouched.
        for item in plan:
            invoice_id, supplier_id, rows = item["invoice_id"], item["supplier_id"], item["rows"]
            try:
                repo.replace_document_numbers(invoice_id, supplier_id, rows)
            except _COLLISION_ERRORS:
                other = _find_conflicting_owner(repo, invoice_id, supplier_id, rows)
                collisions.append({
                    "invoice_id": invoice_id,
                    "supplier_id": supplier_id,
                    "series": other["series"] if other else (rows[0]["series"] if rows else None),
                    "document_number": other["document_number"] if other else None,
                    "other_invoice_id": other["other_invoice_id"] if other else None,
                })
                continue
            rows_written += len(rows)
    else:
        # No writes happen in dry-run, so there is no DB constraint to catch
        # a collision — predict it instead: a duplicate (supplier, series,
        # document_number) claimed by two DIFFERENT invoice_ids among the
        # numbers this run would allocate. First invoice (id order) keeps the
        # number; later ones reusing it are reported exactly like the
        # apply-mode DB rejection would report them.
        owner_of: dict[tuple, int] = {}
        for item in plan:
            invoice_id, supplier_id, rows = item["invoice_id"], item["supplier_id"], item["rows"]
            conflict = None
            for r in rows:
                if r["document_number"] is None:
                    continue
                key = (supplier_id, r["series"], r["document_number"])
                owner = owner_of.get(key)
                if owner is not None and owner != invoice_id:
                    conflict = (key, owner)
                    break

            if conflict is not None:
                (s_id, series, doc_no), other_invoice_id = conflict
                collisions.append({
                    "invoice_id": invoice_id,
                    "supplier_id": s_id,
                    "series": series,
                    "document_number": doc_no,
                    "other_invoice_id": other_invoice_id,
                })
                continue

            for r in rows:
                if r["document_number"] is not None:
                    owner_of[(supplier_id, r["series"], r["document_number"])] = invoice_id
            rows_written += len(rows)

    return {
        "invoices": len(invoices),
        "rows_written": rows_written,
        "base_mismatches": base_mismatches,
        "collisions": collisions,
        "skipped": skipped,
    }


def _main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually write to facturare_document_numbers (default: dry run).")
    args = parser.parse_args()

    result = backfill(apply=args.apply)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] invoices={result['invoices']} rows_written={result['rows_written']} "
          f"base_mismatches={len(result['base_mismatches'])} "
          f"collisions={len(result['collisions'])} skipped={len(result['skipped'])}")

    if result["base_mismatches"]:
        print("BASE MISMATCHES (refused to write) — must fix before proceeding:")
        print(json.dumps(result["base_mismatches"], indent=2, default=str))
    if result["collisions"]:
        print("COLLISIONS (invoice skipped, needs manual resolution):")
        print(json.dumps(result["collisions"], indent=2, default=str))
    if result["skipped"]:
        print("SKIPPED (could not resolve lines/supplier):")
        print(json.dumps(result["skipped"], indent=2, default=str))


if __name__ == "__main__":
    _main()
