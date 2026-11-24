"""Idempotent backfill: stamp carpark_vehicle_revenues.exchange_rate_eur for
existing non-EUR revenues that have no rate, from the BNR rate at each revenue's
date (units of the revenue's currency per 1 EUR). RON stays the source of truth;
only the rate is added. A revenue whose date has no BNR rate goes to
`needs_review` — never guessed, never written. Mirror of
backfill_cost_exchange_rate.py.

Usage — dry-run by default:
    cd jarvis && python -m scripts.backfill_revenue_exchange_rate
Apply:
    cd jarvis && python -m scripts.backfill_revenue_exchange_rate --apply [--company <id>]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db  # noqa: E402
from core.services.currency_converter import get_exchange_rate  # noqa: E402

AUDIT_SQL = """
    SELECT id, currency, amount, date
    FROM carpark_vehicle_revenues
    WHERE currency IS NOT NULL AND currency <> 'EUR'
      AND (exchange_rate_eur IS NULL OR exchange_rate_eur = 0)
"""
COMPANY_FILTER = """
      AND vehicle_id IN (SELECT id FROM carpark_vehicles WHERE company_id = %s)
"""
UPDATE_SQL = "UPDATE carpark_vehicle_revenues SET exchange_rate_eur = %s WHERE id = %s"


def rate_for(currency, rev_date):
    """BNR rate = units of `currency` per 1 EUR at rev_date (RON directly; other
    currencies via the RON cross-rate). Returns None when BNR has no rate."""
    if not rev_date:
        return None
    d = str(rev_date)[:10]
    if currency == 'RON':
        return get_exchange_rate('EUR', d)
    eur = get_exchange_rate('EUR', d)
    cur = get_exchange_rate(currency, d)
    return (eur / cur) if (eur and cur and float(cur) > 0) else None


def audit(cursor, company_id=None):
    """Read-only list of non-EUR revenues with no exchange_rate_eur."""
    if company_id is None:
        cursor.execute(AUDIT_SQL + " ORDER BY id")
    else:
        cursor.execute(AUDIT_SQL + COMPANY_FILTER + " ORDER BY id", (company_id,))
    rows = cursor.fetchall()
    print(f"Audit: {len(rows)} non-EUR revenue(s) with no exchange_rate_eur.")
    return rows


def run(apply=False, company_id=None):
    """Audit (always) + set exchange_rate_eur (dry-run unless apply=True).

    Returns {'audited': [ids], 'updated': [ids], 'needs_review': [ids]}.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        rows = audit(cursor, company_id)
        updated, needs_review = [], []
        for row in rows:
            rate = rate_for(row['currency'], row['date'])
            if not rate or float(rate) <= 0:
                needs_review.append(row['id'])
                print(f"  NEEDS REVIEW id={row['id']}: no BNR rate for "
                      f"{row['currency']} on {row['date']} — not written.")
                continue
            rate = round(float(rate), 4)
            if apply:
                cursor.execute(UPDATE_SQL, (rate, row['id']))
                print(f"  SET id={row['id']}: exchange_rate_eur -> {rate} "
                      f"({row['currency']} {row['date']})")
            else:
                print(f"  WOULD SET id={row['id']}: exchange_rate_eur -> {rate} (dry-run)")
            updated.append(row['id'])
        if apply:
            conn.commit()
        mode = 'APPLIED' if apply else 'DRY-RUN (pass --apply to write)'
        print(f"\nSummary [{mode}]: set {len(updated)}, needs_review {len(needs_review)}.")
        return {'audited': [r['id'] for r in rows], 'updated': updated,
                'needs_review': needs_review}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def main():
    parser = argparse.ArgumentParser(
        description='Backfill exchange_rate_eur on existing non-EUR carpark revenues from BNR.')
    parser.add_argument('--apply', action='store_true',
                        help='Write the rates. Default is dry-run (audit + preview only).')
    parser.add_argument('--company', type=int, default=None,
                        help='Scope to a single company_id (safe staging runs).')
    args = parser.parse_args()
    run(apply=args.apply, company_id=args.company)


if __name__ == '__main__':
    main()
