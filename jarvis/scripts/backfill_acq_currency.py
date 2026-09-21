"""Idempotent backfill: migrate legacy RON-convention `carpark_vehicles` rows
to the canonical acquisition-price convention.

Canonical (import-created convention; all current prod data + every other
CarPark write path — see carpark/money.py):
    acquisition_price    = GROSS EUR
    purchase_price_net   = NET EUR
    acquisition_currency = 'EUR'

Legacy editor-write-path convention (acquisition_currency = 'RON'):
    acquisition_price = NET LEI (purchase_price_net/acquisition_currency were
    never reconciled to canonical by that write path)

There are currently 0 such rows on prod (see acquisitionCanonical.ts /
carpark/money.py docstrings) — this script is a safety net for staging seed
data and any future regression in the editor write-path, per
docs/superpowers/plans/2026-09-21-carpark-acq-currency-reconciliation.md
Task 8.

Usage — dry-run by default (audits + prints what WOULD change, writes nothing):
    cd jarvis && python -m scripts.backfill_acq_currency

Apply the conversion for real (targets whatever DATABASE_URL is configured):
    cd jarvis && python -m scripts.backfill_acq_currency --apply

Every UPDATE is guarded by `WHERE id = %s AND acquisition_currency = 'RON'`,
so a row that has already been converted no longer matches on a re-run —
idempotent by construction, safe to run repeatedly (e.g. after fixing a kurs
manually for a row that was flagged for review).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db  # noqa: E402

AUDIT_SQL = """
    SELECT id, source, acquisition_currency, acquisition_price, purchase_price_net,
           acquisition_exchange_rate, purchase_vat_rate
    FROM carpark_vehicles
    WHERE acquisition_currency = 'RON'
    ORDER BY id
"""

UPDATE_SQL = """
    UPDATE carpark_vehicles
    SET acquisition_price = %s, purchase_price_net = %s, acquisition_currency = 'EUR'
    WHERE id = %s AND acquisition_currency = 'RON'
"""


def audit(cursor):
    """Read-only audit of legacy RON-convention rows. Always prints; returns the rows.

    Never writes anything — safe to call on its own (e.g. for a staging
    dry-run check) independent of `convert_rows`/`run`.
    """
    cursor.execute(AUDIT_SQL)
    rows = cursor.fetchall()
    print(f"Audit: {len(rows)} row(s) with acquisition_currency = 'RON' "
          f"(legacy editor-convention rows):")
    for row in rows:
        print(f"  id={row['id']} source={row['source']!r} "
              f"acquisition_price(NET LEI)={row['acquisition_price']} "
              f"purchase_price_net={row['purchase_price_net']} "
              f"acquisition_exchange_rate={row['acquisition_exchange_rate']} "
              f"purchase_vat_rate={row['purchase_vat_rate']}")
    return rows


def compute_conversion(row):
    """Compute the canonical (gross_eur, net_eur) pair for one RON-convention row.

    netLei = acquisition_price (NET LEI); gross EUR = netLei*(1+vat/100)/kurs;
    net EUR = netLei/kurs — mirrors acquisitionCanonical.ts's toCanonical().

    Returns None when the row has no usable, valid (> 0) exchange rate or no
    price to convert — those rows must be surfaced for manual review, never
    guessed at.
    """
    kurs = row['acquisition_exchange_rate']
    net_lei = row['acquisition_price']
    if kurs is None or net_lei is None:
        return None
    kurs = float(kurs)
    net_lei = float(net_lei)
    if kurs <= 0:
        return None
    vat = float(row['purchase_vat_rate'] or 0)
    gross_eur = round(net_lei * (1 + vat / 100) / kurs, 2)
    net_eur = round(net_lei / kurs, 2)
    return gross_eur, net_eur


def convert_rows(cursor, rows, apply=False):
    """Convert every RON-convention row in `rows` to canonical EUR.

    Dry-run by default (apply=False): prints what WOULD change, writes nothing.
    apply=True executes the guarded UPDATE for each convertible row (see
    module docstring for the idempotency guard).

    Returns (converted_ids, manual_review_ids). `converted_ids` lists rows
    that were successfully converted (apply=True) or would be (apply=False);
    `manual_review_ids` lists rows with no valid exchange rate/price, which
    are never written to regardless of `apply`.
    """
    converted = []
    manual_review = []
    for row in rows:
        result = compute_conversion(row)
        if result is None:
            manual_review.append(row['id'])
            print(f"  NEEDS MANUAL REVIEW id={row['id']}: no valid exchange rate/price "
                  f"(acquisition_exchange_rate={row['acquisition_exchange_rate']!r}, "
                  f"acquisition_price={row['acquisition_price']!r}) — not converted, "
                  f"not guessed at.")
            continue

        gross_eur, net_eur = result
        if apply:
            cursor.execute(UPDATE_SQL, (gross_eur, net_eur, row['id']))
            print(f"  CONVERTED id={row['id']}: acquisition_price -> {gross_eur} EUR, "
                  f"purchase_price_net -> {net_eur} EUR, acquisition_currency -> 'EUR'")
        else:
            print(f"  WOULD CONVERT id={row['id']}: acquisition_price -> {gross_eur} EUR, "
                  f"purchase_price_net -> {net_eur} EUR (dry-run; pass --apply to write)")
        converted.append(row['id'])
    return converted, manual_review


def run(apply=False):
    """Full backfill: audit (always, read-only) + convert (dry-run unless
    apply=True) + summary.

    Returns {'audited': [ids], 'converted': [ids], 'manual_review': [ids]}.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        rows = audit(cursor)
        if not rows:
            print("Nothing to convert.")
            return {'audited': [], 'converted': [], 'manual_review': []}

        converted, manual_review = convert_rows(cursor, rows, apply=apply)
        if apply:
            conn.commit()

        mode = 'APPLIED' if apply else 'DRY-RUN (pass --apply to write)'
        print(f"\nSummary [{mode}]: converted {len(converted)}, "
              f"skipped {len(manual_review)} for manual review.")
        return {
            'audited': [row['id'] for row in rows],
            'converted': converted,
            'manual_review': manual_review,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def main():
    parser = argparse.ArgumentParser(
        description='Migrate legacy RON-convention carpark_vehicles rows to canonical EUR.')
    parser.add_argument('--apply', action='store_true',
                         help='Write the conversion. Default is dry-run (audit + preview only).')
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == '__main__':
    main()
