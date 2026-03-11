#!/usr/bin/env python3
"""
Migration: Legacy Jarvis → New Jarvis (staging)

Table groups (selectable):
  invoices   → invoices, allocations, reinvoice_destinations
  statements → bank_statements, bank_statement_transactions
  hr         → hr.events, hr.event_bonuses

Strategy:
  - TRUNCATE only selected target tables (CASCADE)
  - INSERT all rows from legacy preserving original IDs
  - NULL out user FKs that don't exist in target DB
  - Handle bank_statement_transactions.merged_into_id self-reference in 2 passes
  - Reset all sequences after insert

Usage:
  python3 scripts/migrate_legacy_to_new.py [--dry-run] [--only invoices,statements,hr]
  python3 scripts/migrate_legacy_to_new.py --only invoices          # just invoices group
  python3 scripts/migrate_legacy_to_new.py --only invoices,hr       # invoices + hr
  python3 scripts/migrate_legacy_to_new.py                          # all (default)
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

ALL_GROUPS = ["invoices", "statements", "hr"]

# Parse --only flag
SELECTED_GROUPS = set(ALL_GROUPS)
for i, arg in enumerate(sys.argv):
    if arg == "--only" and i + 1 < len(sys.argv):
        raw = sys.argv[i + 1].split(",")
        invalid = [g for g in raw if g not in ALL_GROUPS]
        if invalid:
            print(f"ERROR: Unknown group(s): {', '.join(invalid)}")
            print(f"  Valid groups: {', '.join(ALL_GROUPS)}")
            sys.exit(1)
        SELECTED_GROUPS = set(raw)
        break

# Tables that belong to each group (for truncate)
GROUP_TABLES = {
    "invoices": [
        "reinvoice_destinations",
        "allocations",
        "notification_log",
        "invoices",
    ],
    "statements": [
        "bank_statement_transactions",
        "bank_statements",
    ],
    "hr": [
        "hr.event_bonuses",
        "hr.events",
    ],
}


def safe_uid(uid, valid_ids):
    return uid if uid in valid_ids else None


def migrate():
    groups_label = ", ".join(sorted(SELECTED_GROUPS))
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Groups: {groups_label}")
    print("Connecting to databases...")
    legacy = psycopg2.connect(LEGACY_DSN)
    new = psycopg2.connect(NEW_DSN)

    try:
        with new:
            with new.cursor() as cur:
                # ── Valid user IDs in target DB ─────────────────────────────
                cur.execute("SELECT id FROM users")
                valid_users = {r[0] for r in cur.fetchall()}
                print(f"Target DB has {len(valid_users)} users")

                # ── TRUNCATE only selected tables ─────────────────────────
                tables_to_truncate = []
                for g in SELECTED_GROUPS:
                    tables_to_truncate.extend(GROUP_TABLES[g])

                print(f"\nTruncating: {', '.join(tables_to_truncate)}...")
                if not DRY_RUN:
                    cur.execute(
                        f"TRUNCATE TABLE {', '.join(tables_to_truncate)}"
                        f" RESTART IDENTITY CASCADE"
                    )
                    print("  ✓ Truncated")
                else:
                    print("  [skipped in dry-run]")

                with legacy.cursor() as lc:

                    # ═══════════════════════════════════════════════════════
                    # GROUP: invoices
                    # ═══════════════════════════════════════════════════════
                    if "invoices" in SELECTED_GROUPS:

                        # ── invoices ──────────────────────────────────────
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
                                "SELECT setval('invoices_id_seq', COALESCE((SELECT MAX(id) FROM invoices), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                        # ── allocations ───────────────────────────────────
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
                                "SELECT setval('allocations_id_seq', COALESCE((SELECT MAX(id) FROM allocations), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                        # ── reinvoice_destinations ─────────────────���──────
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
                                " COALESCE((SELECT MAX(id) FROM reinvoice_destinations), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                    # ═══════════════════════════════════════════════════════
                    # GROUP: statements
                    # ═══════════════════════════════════════════════════════
                    if "statements" in SELECTED_GROUPS:

                        # ── bank_statements ───────────────────────────────
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
                                " COALESCE((SELECT MAX(id) FROM bank_statements), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                        # ── bank_statement_transactions ───────────────────
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
                        merged_map = {r[0]: r[25] for r in rows if r[25] is not None}
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
                            if merged_map:
                                merge_rows = [(mid, rid) for rid, mid in merged_map.items()]
                                execute_values(cur,
                                    "UPDATE bank_statement_transactions AS t"
                                    " SET merged_into_id = v.mid"
                                    " FROM (VALUES %s) AS v(mid, rid)"
                                    " WHERE t.id = v.rid",
                                    merge_rows, page_size=500
                                )
                                print(f"  Restored {len(merged_map)} merged_into_id links")
                            cur.execute(
                                "SELECT setval('bank_statement_transactions_id_seq',"
                                " COALESCE((SELECT MAX(id) FROM bank_statement_transactions), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                    # ═══════════════════════════════════════════════════════
                    # GROUP: hr
                    # ═══════════════════════════════════════════════════════
                    if "hr" in SELECTED_GROUPS:

                        # ── hr.events ─────────────────────────────────────
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
                                "SELECT setval('hr.events_id_seq', COALESCE((SELECT MAX(id) FROM hr.events), 1))"
                            )
                            print("  ✓ Inserted + sequence reset")

                        # ── hr.event_bonuses ──────────────────────────────
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
                                " COALESCE((SELECT MAX(id) FROM hr.event_bonuses), 1))"
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
