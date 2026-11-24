"""Idempotent backfill: migrate legacy `carpark_vehicles.cost_lines` JSON
(freeform acquisition cost lines, written by the pre-unification
VehicleForm/Detail editor — see schema_incremental.py's "freeform
acquisition cost lines" column comment) into structured
`carpark_vehicle_costs` rows under a new `achizitie` cost line (registered
in the cost-model-unification Task 1), then nulls `cost_lines`.

This is accounting-sensitive: a double-count or VAT inflation would
silently corrupt car economics (the floor-price / profitability engine and
the Fișă de preț composer both read landed cost from EITHER the legacy
`cost_lines` JSON OR the structured `achizitie` costs — never both at once,
by design). The whole point of nulling `cost_lines` in the SAME transaction
as creating the structured rows is to guarantee that invariant: it must be
impossible to observe a committed state where a car has BOTH new achizitie
rows AND a non-null cost_lines.

Per-vehicle migration, in ONE transaction (commit per car, for resumability
— a crash mid-run leaves already-migrated cars durably migrated and
unmigrated cars untouched; the next invocation picks up exactly where it
left off):
  1. get_or_create the `achizitie` cost line for the vehicle (currency='EUR',
     planned_amount=0) — raw SQL, NOT CostLineRepository.get_or_create_for_type.
     That helper (and CostLineRepository.create_cost/recalc_spent) each
     open+commit their OWN connection per call, which would break the
     per-car atomicity this script requires. This is a deliberate
     re-expression of that repository's semantics on this script's own
     cursor, not duplication-to-avoid.
  2. For every JSON entry with a numeric, non-null `eur`: INSERT one
     carpark_vehicle_costs row — cost_type='achizitie', amount=eur,
     currency='EUR', vat_rate=0, vat_amount=0 (EXPLICIT: the column DEFAULTs
     are 19/0, and letting those defaults apply would silently inflate the
     floor-price's total_with_vat for a cost that was already a plain cash
     number with no VAT component in the legacy JSON).
  3. recalc_spent the line from SUM(amount) — mirrors
     CostLineRepository.recalc_spent exactly.
  4. UPDATE carpark_vehicles SET cost_lines = NULL WHERE id = %s.
  5. conn.commit() for this car.

Idempotency: the predicate for "needs migrating" is `cost_lines IS NOT NULL
AND cost_lines <> ''` (see `audit()`) — NOT "vehicle has no achizitie line".
A migrated car has cost_lines = NULL, so a re-run is a true no-op for it. A
car that already has an achizitie line — e.g. a user manually added an
achizitie cost in the window before this backfill ran (a separate, accepted
race; see Task 4 brief CARRY-IN) — gets its migrated child rows APPENDED to
that existing line rather than spawning a second one. An entry with a
null/non-numeric `eur` is skipped (never a null-amount INSERT); a car whose
every entry is skippable still gets `cost_lines` nulled (its usable total
was 0, not "nothing to do").

Data safety: a car whose non-empty `cost_lines` is MALFORMED (invalid JSON,
or valid JSON that isn't a list) is NEVER nulled and NEVER migrated — it is
surfaced in a `needs_review` bucket (in the return dict and the audit/summary
prints) so an operator inspects it before the prod `--apply`. Silently
nulling a malformed-but-non-empty accounting column would be irreversible
data loss (controller ruling). Only a clean parse that yielded no usable
money (empty list / all-skippable entries) is nulled, because we then KNOW
there was nothing to migrate.

Usage — dry-run by default (audits + prints what WOULD migrate, writes nothing):
    cd jarvis && python -m scripts.backfill_cost_lines_to_structured

Apply for real (targets whatever DATABASE_URL is configured):
    cd jarvis && python -m scripts.backfill_cost_lines_to_structured --apply

Scope to one company (safe staged rollout, or tests):
    cd jarvis && python -m scripts.backfill_cost_lines_to_structured --apply --company 123
"""
import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db  # noqa: E402

AUDIT_SQL = """
    SELECT id, cost_lines, acquisition_date, created_at
    FROM carpark_vehicles
    WHERE cost_lines IS NOT NULL AND cost_lines <> ''
"""

AUDIT_SQL_COMPANY_FILTER = "\n    AND company_id = %s"

AUDIT_SQL_ORDER = "\n    ORDER BY id"

GET_LINE_SQL = """
    SELECT id FROM carpark_vehicle_cost_lines
    WHERE vehicle_id = %s AND cost_type = 'achizitie'
    ORDER BY id LIMIT 1
"""

CREATE_LINE_SQL = """
    INSERT INTO carpark_vehicle_cost_lines (vehicle_id, cost_type, planned_amount, currency)
    VALUES (%s, 'achizitie', 0, 'EUR')
    RETURNING id
"""

INSERT_COST_SQL = """
    INSERT INTO carpark_vehicle_costs
        (vehicle_id, cost_line_id, cost_type, description, amount, currency,
         vat_rate, vat_amount, observation, date)
    VALUES (%s, %s, 'achizitie', %s, %s, 'EUR', 0, 0, %s, %s)
"""

RECALC_SQL = """
    UPDATE carpark_vehicle_cost_lines SET
        spent_amount = COALESCE(
            (SELECT SUM(amount) FROM carpark_vehicle_costs WHERE cost_line_id = %s), 0
        ),
        updated_at = NOW()
    WHERE id = %s
"""

NULL_COST_LINES_SQL = "UPDATE carpark_vehicles SET cost_lines = NULL WHERE id = %s"


def parse_lines_strict(raw):
    """Parse the legacy `cost_lines` TEXT column, distinguishing a clean
    parse from a malformed one.

    Returns (ok, entries):
      - ok=True  -> `raw` was None/empty OR valid JSON that is a list;
        `entries` is that list filtered to dict entries (possibly empty).
      - ok=False -> `raw` was NON-empty but could not be parsed into a JSON
        list (invalid JSON, or valid JSON that isn't an array). `entries`
        is []. The caller MUST treat this as "needs manual review" and must
        NOT null the column — silently dropping a malformed-but-non-empty
        cost_lines on a prod accounting migration would be irreversible
        data loss (controller ruling).

    An empty/whitespace-only `raw` that happens to be unparseable (e.g. the
    audit SQL already excludes '' but '  ' could slip through) returns
    ok=False too, which is the safe default — we'd rather flag a blank-ish
    value for a human than null it.
    """
    if not raw:
        return True, []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return False, []
    if not isinstance(parsed, list):
        return False, []
    return True, [entry for entry in parsed if isinstance(entry, dict)]


def parse_lines(raw):
    """Parse the legacy `cost_lines` TEXT column -> list[dict].

    Returns [] for None/empty/invalid-JSON/non-list input, and silently
    drops any non-dict array entries — mirrors the frontend's null-safety
    (Detail.tsx's parseCostLines, profitInputs.ts's sumCostLinesEur). This
    collapses "clean but empty" and "malformed" into the same []; callers
    that must NOT null a malformed-but-non-empty column (see `run`) use
    `parse_lines_strict` instead to tell the two apart.
    """
    _ok, entries = parse_lines_strict(raw)
    return entries


def _is_numeric(value):
    """True for an int/float/numeric-string, excluding bool (JSON `true`
    must never be treated as a usable amount) and None."""
    if value is None or isinstance(value, bool):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _parse_entry_date(entry_date):
    """Validate a legacy JSON entry's `date` string, returning it unchanged
    when it's a genuinely parseable ISO date (e.g. '2026-01-02' — the only
    format the date-input editor that wrote this field ever produced), or
    None otherwise.

    A non-empty `date` that is NOT a parseable date (e.g. 'N/A', a
    half-typed value from an old freeform editor, or any other garbage that
    slipped into the legacy JSON) must never reach the INSERT as a raw
    string: Postgres would reject it with an invalid-input-syntax error,
    and because this script commits per-car (see module docstring), that
    exception would propagate out of `run()` and halt the ENTIRE backfill
    on whichever car happens to be malformed — leaving every car after it
    in the audit order unmigrated. Returning None here routes an
    unparseable `date` into the SAME fallback chain as a missing/empty one
    (vehicle acquisition/created date -> CURRENT_DATE), so one bad date
    degrades to "use the fallback" instead of halting the run.
    """
    if not isinstance(entry_date, str):
        return None
    try:
        date.fromisoformat(entry_date.strip())
    except ValueError:
        return None
    return entry_date


def build_cost_row(entry, vehicle):
    """Build the carpark_vehicle_costs insert payload for one legacy JSON
    entry, or return None when the entry has no usable `eur`.

    Entry shape (current VehicleForm/Detail convention):
        {type, description, date, lei, kurs, eur}
    Legacy fallback (the original freeform shape, pre-type/date/lei/kurs —
    see schema_incremental.py's "[{label, amount}]" column comment):
        {label, amount}
    Only `eur` (or the `amount` fallback) is ever money — `lei`/`kurs` are
    provenance only, folded into `observation`, never summed as an amount.

    `vehicle` supplies the date fallback chain for a missing/empty/
    UNPARSEABLE entry.date (e.g. 'N/A'): vehicle['acquisition_date'] ->
    vehicle['created_at'] -> today (CURRENT_DATE). `vehicle` may be a plain
    dict (as used by the pure-function tests) or a RealDictCursor row (as
    used by `run()`).
    """
    eur = entry.get('eur', entry.get('amount'))
    if not _is_numeric(eur):
        return None
    amount = float(eur)

    type_label = (entry.get('type') or entry.get('label') or '').strip()
    description_text = (entry.get('description') or '').strip()
    if type_label and description_text:
        description = f'{type_label}: {description_text}'
    elif type_label:
        description = type_label
    else:
        description = description_text or None

    lei = entry.get('lei')
    kurs = entry.get('kurs')
    provenance_parts = []
    if lei is not None:
        provenance_parts.append(f'LEI={lei}')
    if kurs is not None:
        provenance_parts.append(f'kurs={kurs}')
    observation = 'Migrat din cost_lines achiziție'
    if provenance_parts:
        observation += '; ' + ' '.join(provenance_parts)

    entry_date = _parse_entry_date(entry.get('date') or None)
    if entry_date:
        date_value = entry_date
    else:
        acquisition_date = vehicle.get('acquisition_date')
        created_at = vehicle.get('created_at')
        if acquisition_date:
            date_value = acquisition_date
        elif created_at:
            date_value = created_at.date() if hasattr(created_at, 'date') else created_at
        else:
            date_value = date.today()

    return {
        'cost_type': 'achizitie',
        'description': description,
        'amount': amount,
        'currency': 'EUR',
        'vat_rate': 0,
        'vat_amount': 0,
        'observation': observation,
        'date': date_value,
    }


def audit(cursor, company_id=None):
    """Read-only audit of vehicles with a non-empty `cost_lines`. Always
    prints; returns the rows. Never writes anything — safe to call on its
    own (e.g. for a staging dry-run check) independent of `run`.

    company_id=None (default) audits the whole table — the prod backfill
    behavior. When a company_id is given, the audit (and therefore the
    migration downstream) is scoped to that company's rows only, so tests
    can operate purely on their own sentinel company without touching
    real/other-company data.
    """
    if company_id is None:
        cursor.execute(AUDIT_SQL + AUDIT_SQL_ORDER)
    else:
        cursor.execute(AUDIT_SQL + AUDIT_SQL_COMPANY_FILTER + AUDIT_SQL_ORDER, (company_id,))
    rows = cursor.fetchall()

    total_entries = 0
    total_usable_eur = 0.0
    malformed_ids = []
    for row in rows:
        ok, entries = parse_lines_strict(row['cost_lines'])
        if not ok:
            malformed_ids.append(row['id'])
            continue
        total_entries += len(entries)
        for entry in entries:
            built = build_cost_row(entry, row)
            if built is not None:
                total_usable_eur += built['amount']

    print(f"Audit: {len(rows)} vehicle(s) with non-empty cost_lines "
          f"({total_entries} JSON entr{'y' if total_entries == 1 else 'ies'}, "
          f"{total_usable_eur:.2f} EUR usable total):")
    for row in rows:
        ok, entries = parse_lines_strict(row['cost_lines'])
        if ok:
            print(f"  id={row['id']} entries={len(entries)}")
        else:
            print(f"  id={row['id']} MALFORMED cost_lines "
                  f"(not parseable as a JSON list) -> NEEDS REVIEW, will NOT be nulled")
    if malformed_ids:
        print(f"  !! {len(malformed_ids)} vehicle(s) have MALFORMED cost_lines "
              f"and will be left untouched for manual review: {malformed_ids}")
    return rows


def run(apply=False, company_id=None):
    """Full backfill: audit (always, read-only) + migrate (dry-run unless
    apply=True), one transaction (commit) per vehicle + summary.

    company_id=None (default) processes the whole table — the prod backfill
    behavior. Pass a company_id to scope both audit and migration to that
    single company (used by the DB-backed tests so they only ever touch
    their own sentinel rows, and to allow a safe staged rollout on prod).

    Returns {'audited': [ids], 'migrated': [ids], 'skipped': [ids],
             'needs_review': [ids]}.
    `migrated` lists vehicles that had >= 1 usable cost entry (rows were/
    would be inserted); `skipped` lists vehicles whose cost_lines parsed
    cleanly to a valid list but yielded no usable money (empty list, or
    every entry had a null/non-numeric eur) — those are nulled, we KNOW
    there was nothing to migrate. `needs_review` lists vehicles whose
    NON-empty cost_lines could NOT be parsed into a JSON list (malformed):
    those are left completely untouched (not migrated, NOT nulled) so an
    operator can inspect them before a prod --apply — silently nulling a
    malformed-but-non-empty accounting column would be irreversible data
    loss (controller ruling).
    """
    conn = get_db()
    try:
        # get_db() returns an autocommit=True connection (database.py), which
        # would make every statement below self-commit and turn the per-car
        # conn.commit() into a no-op — reopening the forbidden window where a
        # car has BOTH structured achizitie rows AND non-null cost_lines, and
        # leaving a car PERMANENTLY half-migrated on a mid-car failure. Turn
        # autocommit OFF so the per-car commit is a real atomic boundary
        # (INSERTs + NULL land together or not at all) and rollback is
        # meaningful. release_db() resets autocommit=False on return, so this
        # does not contaminate the pooled connection either way.
        conn.autocommit = False
        cursor = get_cursor(conn)
        rows = audit(cursor, company_id=company_id)
        if not rows:
            print("Nothing to migrate.")
            return {'audited': [], 'migrated': [], 'skipped': [], 'needs_review': []}

        migrated = []
        skipped = []
        needs_review = []
        for row in rows:
            vehicle_id = row['id']
            ok, entries = parse_lines_strict(row['cost_lines'])

            if not ok:
                # Malformed non-empty cost_lines: never null, never migrate.
                needs_review.append(vehicle_id)
                print(f"  NEEDS REVIEW id={vehicle_id}: cost_lines is non-empty but not "
                      f"parseable as a JSON list — left untouched (not nulled, not migrated)")
                continue

            built_rows = [b for b in (build_cost_row(e, row) for e in entries) if b is not None]

            if not apply:
                if built_rows:
                    migrated.append(vehicle_id)
                    total = sum(b['amount'] for b in built_rows)
                    print(f"  WOULD MIGRATE id={vehicle_id}: {len(built_rows)} cost row(s), "
                          f"{total:.2f} EUR total (dry-run; pass --apply to write)")
                else:
                    skipped.append(vehicle_id)
                    print(f"  WOULD NULL cost_lines id={vehicle_id}: 0 usable entries (dry-run)")
                continue

            # ── apply=True: everything below for this one vehicle commits
            #    together, or none of it does (see module docstring). ──
            line_id = None
            if built_rows:
                cursor.execute(GET_LINE_SQL, (vehicle_id,))
                existing_line = cursor.fetchone()
                if existing_line:
                    line_id = existing_line['id']
                else:
                    cursor.execute(CREATE_LINE_SQL, (vehicle_id,))
                    line_id = cursor.fetchone()['id']

                for built in built_rows:
                    cursor.execute(INSERT_COST_SQL, (
                        vehicle_id, line_id, built['description'], built['amount'],
                        built['observation'], built['date'],
                    ))

                cursor.execute(RECALC_SQL, (line_id, line_id))

            cursor.execute(NULL_COST_LINES_SQL, (vehicle_id,))
            conn.commit()

            if built_rows:
                migrated.append(vehicle_id)
                print(f"  MIGRATED id={vehicle_id}: {len(built_rows)} cost row(s) -> "
                      f"achizitie line {line_id}, cost_lines nulled")
            else:
                skipped.append(vehicle_id)
                print(f"  NULLED cost_lines id={vehicle_id}: 0 usable entries "
                      f"(every JSON entry had a null/non-numeric eur)")

        mode = 'APPLIED' if apply else 'DRY-RUN (pass --apply to write)'
        print(f"\nSummary [{mode}]: migrated {len(migrated)}, skipped {len(skipped)} "
              f"(cost_lines nulled with zero usable entries), "
              f"needs_review {len(needs_review)} (malformed cost_lines left untouched).")
        if needs_review:
            print(f"  !! Inspect these {len(needs_review)} malformed vehicle(s) before "
                  f"re-running --apply: {needs_review}")
        return {
            'audited': [row['id'] for row in rows],
            'migrated': migrated,
            'skipped': skipped,
            'needs_review': needs_review,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def main():
    parser = argparse.ArgumentParser(
        description='Migrate legacy carpark_vehicles.cost_lines JSON into structured achizitie cost rows.')
    parser.add_argument('--apply', action='store_true',
                         help='Write the migration. Default is dry-run (audit + preview only).')
    parser.add_argument('--company', type=int, default=None,
                         help='Scope the backfill to a single company_id (for a staged rollout).')
    args = parser.parse_args()
    run(apply=args.apply, company_id=args.company)


if __name__ == '__main__':
    main()
