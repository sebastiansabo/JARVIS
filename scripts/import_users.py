#!/usr/bin/env python3
"""
Import users from docs/users.xls, matching emails from docs/Alocare licente Microsoft 2026.xlsx.
Users without an email match are skipped.

Usage:
    DATABASE_URL="postgresql://localhost/defaultdb" python3 scripts/import_users.py
    DATABASE_URL="postgresql://localhost/defaultdb" python3 scripts/import_users.py --dry-run
    DATABASE_URL="postgresql://localhost/defaultdb" python3 scripts/import_users.py --default-password "MyPass123"
"""

import argparse
import os
import sys
from collections import defaultdict
from html.parser import HTMLParser

import psycopg2
from werkzeug.security import generate_password_hash

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
USERS_XLS = os.path.join(ROOT_DIR, "docs", "users.xls")
MS_XLSX = os.path.join(ROOT_DIR, "docs", "Alocare licente Microsoft 2026.xlsx")

# ─── HTML table parser (users.xls is HTML in disguise) ────────────────────────

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.current_cell = ""
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = ""
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.current_row.append(self.current_cell.strip())
            self.in_cell = False
        elif tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Lowercase and strip for fuzzy matching."""
    return s.strip().lower()


# ─── Load data ────────────────────────────────────────────────────────────────

def load_users_xls():
    with open(USERS_XLS, encoding="utf-8-sig") as f:
        p = TableParser()
        p.feed(f.read())
    users = []
    for r in p.rows[1:]:  # skip header row
        if len(r) < 2:
            continue
        users.append({
            "first": r[0].strip(),
            "last": r[1].strip(),
            "kiosk_code": r[3].strip() if len(r) > 3 else "",
            "employment_start": r[2].strip() if len(r) > 2 else "",
        })
    return users


def load_ms_xlsx():
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl not installed. Run: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(MS_XLSX)
    ws = wb.active
    entries = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] and row[1]:
            entries.append({
                "name": str(row[0]).strip(),
                "email": str(row[1]).strip().lower(),
                "company": str(row[3]).strip() if row[3] else None,
                "department": str(row[4]).strip() if row[4] else None,
            })
    return entries


def match_users(users, ms_entries):
    """Match users by last name + first word of first name."""
    ms_by_last = defaultdict(list)
    for e in ms_entries:
        parts = e["name"].split()
        if parts:
            ms_by_last[normalize(parts[-1])].append(e)

    for u in users:
        last_key = normalize(u["last"])
        first_words = {normalize(w) for w in u["first"].split()}
        candidates = ms_by_last.get(last_key, [])

        hits = []
        for c in candidates:
            ms_parts = c["name"].split()
            ms_first = normalize(ms_parts[0]) if ms_parts else ""
            if ms_first in first_words:
                hits.append(c)

        if len(hits) == 1:
            u["email"] = hits[0]["email"]
            u["company"] = hits[0]["company"]
            u["department"] = hits[0]["department"]
            u["email_source"] = "microsoft"
        else:
            u["email"] = None
            u["company"] = None
            u["department"] = None
            u["email_source"] = None

    return users


# ─── Import ───────────────────────────────────────────────────────────────────

def import_users(users, password_hash, dry_run):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # Fetch existing emails and names to avoid duplicates
    cur.execute("SELECT lower(email), lower(name) FROM users")
    rows = cur.fetchall()
    existing_emails = {r[0] for r in rows}
    existing_names = {r[1] for r in rows}

    stats = {"inserted": 0, "skipped_duplicate": 0, "skipped_no_email": 0}
    skipped_no_email = []

    for u in users:
        full_name = f"{u['first'].title()} {u['last'].title()}"

        # Resolve email
        email = u.get("email")
        if not email:
            stats["skipped_no_email"] += 1
            skipped_no_email.append(full_name)
            continue

        email_lower = email.lower()
        name_lower = full_name.lower()

        if email_lower in existing_emails or name_lower in existing_names:
            stats["skipped_duplicate"] += 1
            if dry_run:
                reason = "email" if email_lower in existing_emails else "name"
                print(f"  [SKIP duplicate by {reason}] {full_name} <{email}>")
            continue

        if dry_run:
            print(f"  [INSERT] {full_name} <{email}> company={u.get('company')} dept={u.get('department')}")
        else:
            cur.execute(
                """
                INSERT INTO users (name, email, is_active, password_hash, company, department, migrated_from, migrated_at)
                VALUES (%s, %s, true, %s, %s, %s, 'import_users', CURRENT_TIMESTAMP)
                """,
                (
                    full_name,
                    email,
                    password_hash,
                    u.get("company"),
                    u.get("department"),
                ),
            )
            existing_emails.add(email_lower)
            existing_names.add(name_lower)

        stats["inserted"] += 1

    if not dry_run:
        conn.commit()

    cur.close()
    conn.close()
    return stats, skipped_no_email


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import users into JARVIS from XLS + Microsoft licenses file.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--default-password", default="changeme123", help="Default password for imported users (default: changeme123)")
    args = parser.parse_args()

    print(f"Loading users from {USERS_XLS}...")
    users = load_users_xls()
    print(f"  {len(users)} users found")

    print(f"Loading Microsoft licenses from {MS_XLSX}...")
    ms_entries = load_ms_xlsx()
    print(f"  {len(ms_entries)} entries found")

    print("Matching by name...")
    users = match_users(users, ms_entries)
    matched = sum(1 for u in users if u.get("email_source") == "microsoft")
    print(f"  Matched: {matched}/{len(users)} (remaining {len(users)-matched} will be skipped — no email)")

    password_hash = generate_password_hash(args.default_password)

    if args.dry_run:
        print(f"\n--- DRY RUN (password would be: '{args.default_password}') ---\n")
    else:
        print(f"\nImporting with default password: '{args.default_password}'")

    stats, skipped_no_email = import_users(users, password_hash, args.dry_run)

    print(f"\n{'=== DRY RUN RESULTS ===' if args.dry_run else '=== IMPORT COMPLETE ==='}")
    print(f"  {'Would insert' if args.dry_run else 'Inserted'}:   {stats['inserted']}")
    print(f"  Skipped (duplicate): {stats['skipped_duplicate']}")
    print(f"  Skipped (no email):  {stats['skipped_no_email']}")

    if skipped_no_email:
        print(f"\nUsers skipped (no email match):")
        for name in skipped_no_email:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
