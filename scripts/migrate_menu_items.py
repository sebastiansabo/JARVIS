#!/usr/bin/env python3
"""
Migration: Add missing module_menu_items for sidebar-to-settings sync.

Adds: ai_agent, approvals, marketing parent modules + crm_database child under sales.
Also adds 'archived' to the status CHECK constraint.

Usage:
    DATABASE_URL='postgresql://...' python scripts/migrate_menu_items.py
    DATABASE_URL='postgresql://...' python scripts/migrate_menu_items.py --dry-run
"""

import os
import sys
import argparse

import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


PARENT_MODULES = [
    # (module_key, name, description, icon, url, color, status, sort_order)
    ('ai_agent', 'AI Agent', 'AI Assistant & Chat', 'bi-robot', '/ai-agent', '#6366f1', 'active', 1),
    ('approvals', 'Approvals', 'Approval Workflows', 'bi-check2-square', '/approvals', '#f59e0b', 'active', 4),
    ('marketing', 'Marketing', 'Campaigns & Content', 'bi-megaphone', '/marketing', '#ec4899', 'active', 5),
]

# Children: (parent_module_key, module_key, name, description, icon, url, color, status, sort_order)
CHILD_MODULES = [
    ('sales', 'crm_database', 'CRM Database', 'Client & deal management', 'bi-person-lines-fill', '/crm', '#dc3545', 'active', 1),
]


def run(dry_run=False):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # 1. Fix CHECK constraint to allow 'archived'
        print("\n--- Updating status CHECK constraint ---")
        cur.execute("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'module_menu_items'::regclass
              AND contype = 'c'
              AND conname LIKE '%status%'
        """)
        constraints = cur.fetchall()
        for c in constraints:
            print(f"  Dropping constraint: {c['conname']}")
            if not dry_run:
                cur.execute(f"ALTER TABLE module_menu_items DROP CONSTRAINT {c['conname']}")

        print("  Adding new constraint with 'archived' status")
        if not dry_run:
            cur.execute("""
                ALTER TABLE module_menu_items
                ADD CONSTRAINT module_menu_items_status_check
                CHECK (status IN ('active', 'coming_soon', 'hidden', 'archived'))
            """)

        # 2. Add missing parent modules
        print("\n--- Adding missing parent modules ---")
        for mod in PARENT_MODULES:
            module_key = mod[0]
            cur.execute("SELECT id FROM module_menu_items WHERE module_key = %s AND parent_id IS NULL", (module_key,))
            existing = cur.fetchone()
            if existing:
                print(f"  SKIP {module_key} (already exists, id={existing['id']})")
                continue
            print(f"  INSERT {module_key}: {mod[1]}")
            if not dry_run:
                cur.execute("""
                    INSERT INTO module_menu_items (module_key, name, description, icon, url, color, status, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, mod)

        # 3. Add missing child modules
        print("\n--- Adding missing child modules ---")
        for child in CHILD_MODULES:
            parent_key, module_key = child[0], child[1]
            # Find parent
            cur.execute("SELECT id FROM module_menu_items WHERE module_key = %s AND parent_id IS NULL", (parent_key,))
            parent = cur.fetchone()
            if not parent:
                print(f"  SKIP {module_key} (parent '{parent_key}' not found)")
                continue
            # Check if child exists
            cur.execute("SELECT id FROM module_menu_items WHERE module_key = %s AND parent_id = %s", (module_key, parent['id']))
            existing = cur.fetchone()
            if existing:
                print(f"  SKIP {module_key} (already exists under {parent_key}, id={existing['id']})")
                continue
            print(f"  INSERT {module_key} under {parent_key} (parent_id={parent['id']})")
            if not dry_run:
                cur.execute("""
                    INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (parent['id'],) + child[1:])

        # 4. Update sort_order for existing items to make room
        print("\n--- Updating sort order ---")
        cur.execute("""
            SELECT id, module_key, sort_order FROM module_menu_items
            WHERE parent_id IS NULL ORDER BY sort_order
        """)
        all_parents = cur.fetchall()
        desired_order = ['ai_agent', 'accounting', 'hr', 'approvals', 'marketing', 'sales', 'aftersales', 'settings']
        for idx, key in enumerate(desired_order, 1):
            match = next((p for p in all_parents if p['module_key'] == key), None)
            if match and match['sort_order'] != idx:
                print(f"  {key}: sort_order {match['sort_order']} -> {idx}")
                if not dry_run:
                    cur.execute("UPDATE module_menu_items SET sort_order = %s WHERE id = %s", (idx, match['id']))
            elif match:
                print(f"  {key}: sort_order {idx} (ok)")

        if dry_run:
            print("\n--- DRY RUN: no changes committed ---")
            conn.rollback()
        else:
            conn.commit()
            print("\n--- Migration complete ---")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Add missing module menu items')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without applying')
    args = parser.parse_args()
    run(dry_run=args.dry_run)
