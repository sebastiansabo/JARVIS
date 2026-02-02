#!/usr/bin/env python3
"""
Database Migration Script: Consolidate people tables into users

This script merges:
- responsables → users
- hr.employees → users

And updates foreign key references in:
- allocations.responsible → allocations.responsible_user_id
- department_structure.manager → department_structure.manager_user_id

Usage:
    DATABASE_URL='postgresql://...' python scripts/migrate_users.py

Options:
    --dry-run    Show what would be done without making changes
    --phase N    Run only phase N (1-4)
"""

import os
import sys
import argparse
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    """Get database connection."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return psycopg2.connect(db_url)


def phase1_prepare_users_table(conn, dry_run=False):
    """Phase 1: Add necessary columns to users table."""
    print("\n" + "="*60)
    print("PHASE 1: Prepare users table")
    print("="*60)

    cursor = conn.cursor()

    columns_to_add = [
        ("phone", "TEXT"),
        ("is_active", "BOOLEAN DEFAULT TRUE"),
        ("notify_on_allocation", "BOOLEAN DEFAULT TRUE"),
        ("company", "TEXT"),
        ("brand", "TEXT"),
        ("department", "TEXT"),
        ("subdepartment", "TEXT"),
        ("migrated_from", "TEXT"),  # Track source: 'responsable', 'hr_employee'
        ("migrated_at", "TIMESTAMP"),
    ]

    for col_name, col_type in columns_to_add:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = %s
        """, (col_name,))

        if not cursor.fetchone():
            sql = f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
            print(f"  Adding column: {col_name}")
            if not dry_run:
                cursor.execute(sql)
        else:
            print(f"  Column exists: {col_name}")

    if not dry_run:
        conn.commit()
    print("Phase 1 complete.")


def phase2_merge_responsables(conn, dry_run=False):
    """Phase 2: Merge responsables into users (only those with email)."""
    print("\n" + "="*60)
    print("PHASE 2: Merge responsables → users")
    print("="*60)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get responsables WITH valid email only (must contain @)
    cursor.execute("""
        SELECT * FROM responsables
        WHERE email IS NOT NULL AND email != '' AND email LIKE '%@%'
        ORDER BY id
    """)
    responsables = cursor.fetchall()

    # Count skipped (no valid email)
    cursor.execute("""
        SELECT COUNT(*) as count FROM responsables
        WHERE email IS NULL OR email = '' OR email NOT LIKE '%@%'
    """)
    skipped_count = cursor.fetchone()['count']

    print(f"  Found {len(responsables)} responsables with email")
    print(f"  Skipping {skipped_count} responsables without email (will be deleted)")

    stats = {'updated': 0, 'created': 0, 'skipped': skipped_count}

    for resp in responsables:
        # Try to find existing user by email
        user_id = None
        cursor.execute(
            "SELECT id FROM users WHERE LOWER(email) = LOWER(%s)",
            (resp['email'],)
        )
        row = cursor.fetchone()
        if row:
            user_id = row['id']

        if user_id:
            # Update existing user with responsable data
            print(f"  UPDATE user {user_id}: {resp['name']} ({resp['email']})")
            if not dry_run:
                cursor.execute("""
                    UPDATE users SET
                        phone = COALESCE(phone, %s),
                        notify_on_allocation = COALESCE(%s, notify_on_allocation),
                        company = COALESCE(company, %s),
                        brand = COALESCE(brand, %s),
                        department = COALESCE(department, %s),
                        migrated_from = COALESCE(migrated_from || ',', '') || 'responsable',
                        migrated_at = %s
                    WHERE id = %s
                """, (
                    resp['phone'],
                    resp['notify_on_allocation'],
                    resp['company'],
                    resp['brand'],
                    resp['departments'],
                    datetime.now(),
                    user_id
                ))
            stats['updated'] += 1
        else:
            # Create new user from responsable (has email)
            print(f"  CREATE user: {resp['name']} ({resp['email']})")
            if not dry_run:
                cursor.execute("""
                    INSERT INTO users (name, email, phone, notify_on_allocation,
                                       company, brand, department, is_active,
                                       migrated_from, migrated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'responsable', %s)
                """, (
                    resp['name'],
                    resp['email'],
                    resp['phone'],
                    resp['notify_on_allocation'],
                    resp['company'],
                    resp['brand'],
                    resp['departments'],
                    resp.get('is_active', True),
                    datetime.now()
                ))
            stats['created'] += 1

    if not dry_run:
        conn.commit()

    print(f"\nPhase 2 complete: {stats['updated']} updated, {stats['created']} created, {stats['skipped']} skipped (no email)")
    return stats


def phase3_merge_hr_employees(conn, dry_run=False):
    """Phase 3: Link hr.employees to users (don't create new users)."""
    print("\n" + "="*60)
    print("PHASE 3: Link hr.employees → users (no new users created)")
    print("="*60)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get all HR employees
    cursor.execute("SELECT * FROM hr.employees ORDER BY id")
    employees = cursor.fetchall()
    print(f"  Found {len(employees)} HR employees to process")

    stats = {'linked': 0, 'already_linked': 0, 'unmatched': 0}
    unmatched_names = []

    for emp in employees:
        user_id = None

        # First check if already linked via user_id
        if emp.get('user_id'):
            print(f"  ALREADY LINKED: {emp['name']} → user {emp['user_id']}")
            stats['already_linked'] += 1
            continue

        # Try to find user by name
        if emp['name']:
            cursor.execute(
                "SELECT id FROM users WHERE LOWER(name) = LOWER(%s)",
                (emp['name'],)
            )
            row = cursor.fetchone()
            if row:
                user_id = row['id']

        if user_id:
            # Link HR employee to existing user
            print(f"  LINK employee {emp['id']}: {emp['name']} → user {user_id}")
            if not dry_run:
                cursor.execute(
                    "UPDATE hr.employees SET user_id = %s WHERE id = %s",
                    (user_id, emp['id'])
                )
            stats['linked'] += 1
        else:
            # No matching user - skip (don't create)
            unmatched_names.append(emp['name'])
            stats['unmatched'] += 1

    if not dry_run:
        conn.commit()

    print(f"\nPhase 3 complete: {stats['linked']} linked, {stats['already_linked']} already linked, {stats['unmatched']} unmatched")
    if unmatched_names:
        print(f"  Unmatched HR employees (no user): {unmatched_names[:10]}{'...' if len(unmatched_names) > 10 else ''}")
    return stats


def phase4_update_foreign_keys(conn, dry_run=False):
    """Phase 4: Add user_id foreign keys to allocations and department_structure."""
    print("\n" + "="*60)
    print("PHASE 4: Update foreign key references")
    print("="*60)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # 4a. Add responsible_user_id to allocations
    print("\n4a. Adding responsible_user_id to allocations...")
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'allocations' AND column_name = 'responsible_user_id'
    """)
    if not cursor.fetchone():
        print("  Adding column allocations.responsible_user_id")
        if not dry_run:
            cursor.execute("""
                ALTER TABLE allocations
                ADD COLUMN responsible_user_id INTEGER REFERENCES users(id)
            """)

    # Populate responsible_user_id by matching name
    cursor.execute("""
        SELECT DISTINCT responsible FROM allocations
        WHERE responsible IS NOT NULL AND responsible != ''
    """)
    responsibles = [r['responsible'] for r in cursor.fetchall()]
    print(f"  Found {len(responsibles)} unique responsible names to match")

    matched = 0
    unmatched = []
    for name in responsibles:
        cursor.execute(
            "SELECT id FROM users WHERE LOWER(name) = LOWER(%s)",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            if not dry_run:
                cursor.execute("""
                    UPDATE allocations SET responsible_user_id = %s
                    WHERE LOWER(responsible) = LOWER(%s)
                """, (row['id'], name))
            matched += 1
        else:
            unmatched.append(name)

    print(f"  Matched {matched} names to users")
    if unmatched:
        print(f"  UNMATCHED ({len(unmatched)}): {unmatched[:5]}...")

    # 4b. Add manager_user_id to department_structure
    print("\n4b. Adding manager_user_id to department_structure...")
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'department_structure' AND column_name = 'manager_user_id'
    """)
    if not cursor.fetchone():
        print("  Adding column department_structure.manager_user_id")
        if not dry_run:
            cursor.execute("""
                ALTER TABLE department_structure
                ADD COLUMN manager_user_id INTEGER REFERENCES users(id)
            """)

    # Populate manager_user_id by matching name
    cursor.execute("""
        SELECT DISTINCT manager FROM department_structure
        WHERE manager IS NOT NULL AND manager != ''
    """)
    managers = [r['manager'] for r in cursor.fetchall()]
    print(f"  Found {len(managers)} unique manager names to match")

    matched = 0
    for name in managers:
        cursor.execute(
            "SELECT id FROM users WHERE LOWER(name) = LOWER(%s)",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            if not dry_run:
                cursor.execute("""
                    UPDATE department_structure SET manager_user_id = %s
                    WHERE LOWER(manager) = LOWER(%s)
                """, (row['id'], name))
            matched += 1

    print(f"  Matched {matched} managers to users")

    if not dry_run:
        conn.commit()

    print("\nPhase 4 complete.")


def show_summary(conn):
    """Show current state summary."""
    print("\n" + "="*60)
    print("CURRENT DATABASE STATE")
    print("="*60)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    queries = [
        ("Users", "SELECT COUNT(*) as count FROM users"),
        ("Users (migrated)", "SELECT COUNT(*) as count FROM users WHERE migrated_from IS NOT NULL"),
        ("Responsables", "SELECT COUNT(*) as count FROM responsables"),
        ("HR Employees", "SELECT COUNT(*) as count FROM hr.employees"),
        ("HR Employees (linked)", "SELECT COUNT(*) as count FROM hr.employees WHERE user_id IS NOT NULL"),
        ("Allocations", "SELECT COUNT(*) as count FROM allocations"),
        ("Allocations (with user_id)", "SELECT COUNT(*) as count FROM allocations WHERE responsible_user_id IS NOT NULL"),
    ]

    for label, query in queries:
        try:
            cursor.execute(query)
            row = cursor.fetchone()
            print(f"  {label}: {row['count']}")
        except Exception as e:
            print(f"  {label}: N/A ({e})")


def main():
    parser = argparse.ArgumentParser(description='Migrate users database')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--phase', type=int, choices=[1, 2, 3, 4], help='Run only specific phase')
    parser.add_argument('--summary', action='store_true', help='Show current state only')
    args = parser.parse_args()

    conn = get_connection()

    if args.summary:
        show_summary(conn)
        return

    print("="*60)
    print("USER DATABASE MIGRATION")
    print("="*60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Phase: {args.phase or 'ALL'}")

    if args.dry_run:
        print("\n*** DRY RUN - No changes will be made ***\n")

    try:
        if args.phase is None or args.phase == 1:
            phase1_prepare_users_table(conn, args.dry_run)

        if args.phase is None or args.phase == 2:
            phase2_merge_responsables(conn, args.dry_run)

        if args.phase is None or args.phase == 3:
            phase3_merge_hr_employees(conn, args.dry_run)

        if args.phase is None or args.phase == 4:
            phase4_update_foreign_keys(conn, args.dry_run)

        show_summary(conn)

        print("\n" + "="*60)
        print("MIGRATION COMPLETE")
        print("="*60)

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
