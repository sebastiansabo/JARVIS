#!/usr/bin/env python3
"""
Migration: Legacy Jarvis → New Jarvis (staging)

Tables migrated (in dependency order):
  invoices → allocations → reinvoice_destinations
  bank_statements → bank_statement_transactions
  hr.events → hr.event_bonuses

Strategy:
  - TRUNCATE target tables (CASCADE clears dependent rows in notification_log,
    efactura_invoices, mkt_budget_transactions, mkt_project_events)
  - INSERT all rows from legacy preserving original IDs
  - NULL out user FKs that don't exist in target DB
  - Handle bank_statement_transactions.merged_into_id self-reference in 2 passes
  - Reset all sequences after insert

Usage:
  python3 scripts/migrate_legacy_to_new.py [--dry-run]
"""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values

LEGACY_DSN = os.environ.get("LEGACY_DATABASE_URL", "")
NEW_DSN = os.environ.get("DATABASE_URL", "")

if not LEGACY_DSN or not NEW_DSN:
    print("ERROR: Set LEGACY_DATABASE_URL and DATABASE_URL environment variables")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv


def safe_uid(uid, valid_ids):
    return uid if uid in valid_ids else None


def migrate():
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Connecting to databases...")
    legacy = psycopg2.connect(LEGACY_DSN)
    new = psycopg2.connect(NEW_DSN)

    try:
        with new:
            with new.cursor() as cur:
                # ── Valid user IDs in target DB ─────────────────────────────
                cur.execute("SELECT id FROM users")
                valid_users = {r[0] for r in cur.fetchall()}
                print(f"Target DB has {len(valid_users)} users")

                # ── 1. TRUNCATE target tables ───────────────────────────────
                print("\nTruncating target tables (CASCADE)...")
                if not DRY_RUN:
                    cur.execute("""
                        TRUNCATE TABLE
                            hr.event_bonuses,
                            hr.events,
                            reinvoice_destinations,
                            bank_statement_transactions,
                            bank_statements,
                            allocations,
                            notification_log,
                            invoices
                        RESTART IDENTITY CASCADE
                    """)
                    print("  ✓ Truncated")
                else:
                    print("  [skipped in dry-run]")

                with legacy.cursor() as lc:

                    # ── 2. invoices ─────────────────────────────────────────
                    print("\nMigrating invoices...")
                    lc.execute("""
                        SELECT id, supplier, invoice_template, invoice_number, invoice_date,
                               invoice_value, currency, drive_link, comment, created_at, updated_at,
                               value_ron, value_eur, exchange_rate, deleted_at, status,
                               payment_status, vat_rate, subtract_vat, net_value
                        FROM invoices ORDER BY id
                    """)
                    rows = lc.fetchall()
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO invoices (
                                id, supplier, invoice_template, invoice_number, invoice_date,
                                invoice_value, currency, drive_link, comment, created_at, updated_at,
                                value_ron, value_eur, exchange_rate, deleted_at, status,
                                payment_status, vat_rate, subtract_vat, net_value
                            ) VALUES %s
                        """, rows, page_size=500)
                        cur.execute(
                            "SELECT setval('invoices_id_seq', (SELECT MAX(id) FROM invoices))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 3. allocations ──────────────────────────────────────
                    print("\nMigrating allocations...")
                    lc.execute("""
                        SELECT id, invoice_id, company, brand, department, subdepartment,
                               allocation_percent, allocation_value, responsible, reinvoice_to,
                               created_at, reinvoice_department, reinvoice_subdepartment,
                               reinvoice_brand, locked, comment, responsible_user_id
                        FROM allocations ORDER BY id
                    """)
                    rows = lc.fetchall()
                    rows = [r[:16] + (safe_uid(r[16], valid_users),) for r in rows]
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO allocations (
                                id, invoice_id, company, brand, department, subdepartment,
                                allocation_percent, allocation_value, responsible, reinvoice_to,
                                created_at, reinvoice_department, reinvoice_subdepartment,
                                reinvoice_brand, locked, comment, responsible_user_id
                            ) VALUES %s
                        """, rows, page_size=500)
                        cur.execute(
                            "SELECT setval('allocations_id_seq', (SELECT MAX(id) FROM allocations))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 4. reinvoice_destinations ───────────────────────────
                    print("\nMigrating reinvoice_destinations...")
                    lc.execute("""
                        SELECT id, allocation_id, company, brand, department, subdepartment,
                               percentage, value, created_at
                        FROM reinvoice_destinations ORDER BY id
                    """)
                    rows = lc.fetchall()
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO reinvoice_destinations (
                                id, allocation_id, company, brand, department, subdepartment,
                                percentage, value, created_at
                            ) VALUES %s
                        """, rows, page_size=500)
                        cur.execute(
                            "SELECT setval('reinvoice_destinations_id_seq',"
                            " (SELECT MAX(id) FROM reinvoice_destinations))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 5. bank_statements ──────────────────────────────────
                    print("\nMigrating bank_statements...")
                    lc.execute("""
                        SELECT id, filename, file_hash, company_name, company_cui, account_number,
                               period_from, period_to, total_transactions, new_transactions,
                               duplicate_transactions, uploaded_by, uploaded_at
                        FROM bank_statements ORDER BY id
                    """)
                    rows = lc.fetchall()
                    rows = [r[:11] + (safe_uid(r[11], valid_users),) + r[12:] for r in rows]
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO bank_statements (
                                id, filename, file_hash, company_name, company_cui, account_number,
                                period_from, period_to, total_transactions, new_transactions,
                                duplicate_transactions, uploaded_by, uploaded_at
                            ) VALUES %s
                        """, rows, page_size=200)
                        cur.execute(
                            "SELECT setval('bank_statements_id_seq',"
                            " (SELECT MAX(id) FROM bank_statements))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 6. bank_statement_transactions ──────────────────────
                    # Self-reference via merged_into_id: insert with NULL first,
                    # then update merged_into_id in a second pass.
                    print("\nMigrating bank_statement_transactions...")
                    lc.execute("""
                        SELECT id, statement_id, statement_file, company_name, company_cui,
                               account_number, transaction_date, value_date, description,
                               vendor_name, matched_supplier, amount, currency, original_amount,
                               original_currency, exchange_rate, auth_code, card_number,
                               transaction_type, invoice_id, status, created_at,
                               suggested_invoice_id, match_confidence, match_method,
                               merged_into_id, is_merged_result, merged_dates_display
                        FROM bank_statement_transactions ORDER BY id
                    """)
                    rows = lc.fetchall()
                    # Save merged_into_id mapping: {row_id: merged_into_id}
                    merged_map = {r[0]: r[25] for r in rows if r[25] is not None}
                    # Insert with merged_into_id = NULL to avoid self-ref FK issue
                    rows_no_merge = [r[:25] + (None,) + r[26:] for r in rows]
                    print(f"  {len(rows)} rows ({len(merged_map)} with merged_into_id)")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO bank_statement_transactions (
                                id, statement_id, statement_file, company_name, company_cui,
                                account_number, transaction_date, value_date, description,
                                vendor_name, matched_supplier, amount, currency, original_amount,
                                original_currency, exchange_rate, auth_code, card_number,
                                transaction_type, invoice_id, status, created_at,
                                suggested_invoice_id, match_confidence, match_method,
                                merged_into_id, is_merged_result, merged_dates_display
                            ) VALUES %s
                        """, rows_no_merge, page_size=500)
                        # Second pass: restore merged_into_id
                        if merged_map:
                            for row_id, merged_id in merged_map.items():
                                cur.execute(
                                    "UPDATE bank_statement_transactions"
                                    " SET merged_into_id = %s WHERE id = %s",
                                    (merged_id, row_id)
                                )
                            print(f"  Restored {len(merged_map)} merged_into_id links")
                        cur.execute(
                            "SELECT setval('bank_statement_transactions_id_seq',"
                            " (SELECT MAX(id) FROM bank_statement_transactions))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 7. hr.events ────────────────────────────────────────
                    print("\nMigrating hr.events...")
                    lc.execute("""
                        SELECT id, name, start_date, end_date, company, brand, description,
                               created_by, created_at
                        FROM hr.events ORDER BY id
                    """)
                    rows = lc.fetchall()
                    rows = [r[:7] + (safe_uid(r[7], valid_users),) + r[8:] for r in rows]
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO hr.events (
                                id, name, start_date, end_date, company, brand,
                                description, created_by, created_at
                            ) VALUES %s
                        """, rows, page_size=200)
                        cur.execute(
                            "SELECT setval('hr.events_id_seq', (SELECT MAX(id) FROM hr.events))"
                        )
                        print("  ✓ Inserted + sequence reset")

                    # ── 8. hr.event_bonuses ─────────────────────────────────
                    print("\nMigrating hr.event_bonuses...")
                    lc.execute("""
                        SELECT id, user_id, event_id, year, month, participation_start,
                               participation_end, bonus_days, hours_free, bonus_net, details,
                               allocation_month, created_by, created_at, updated_at,
                               bonus_type_id, responsable_id
                        FROM hr.event_bonuses ORDER BY id
                    """)
                    rows = lc.fetchall()
                    rows = [
                        r[:1]
                        + (safe_uid(r[1], valid_users),)   # user_id
                        + r[2:12]
                        + (safe_uid(r[12], valid_users),)  # created_by
                        + r[13:16]
                        + (safe_uid(r[16], valid_users),)  # responsable_id
                        for r in rows
                    ]
                    print(f"  {len(rows)} rows")
                    if not DRY_RUN:
                        execute_values(cur, """
                            INSERT INTO hr.event_bonuses (
                                id, user_id, event_id, year, month, participation_start,
                                participation_end, bonus_days, hours_free, bonus_net, details,
                                allocation_month, created_by, created_at, updated_at,
                                bonus_type_id, responsable_id
                            ) VALUES %s
                        """, rows, page_size=200)
                        cur.execute(
                            "SELECT setval('hr.event_bonuses_id_seq',"
                            " (SELECT MAX(id) FROM hr.event_bonuses))"
                        )
                        print("  ✓ Inserted + sequence reset")

        if DRY_RUN:
            print("\n[DRY RUN complete — no changes made]")
        else:
            print("\n✓ Migration complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback; traceback.print_exc()
        new.rollback()
        sys.exit(1)
    finally:
        legacy.close()
        new.close()


if __name__ == "__main__":
    migrate()
