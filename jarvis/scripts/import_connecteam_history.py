"""Import historical Connecteam 'Bilet de Invoire' submissions from Excel export.

Usage:
    DATABASE_URL=<staging_url> python -m scripts.import_connecteam_history /path/to/export.xlsx
"""

import sys
import os
import hashlib
from datetime import datetime, date, time

import openpyxl
import psycopg2
import psycopg2.extras

FORM_ID = 952672  # Connecteam form ID

STATUS_MAP = {
    'Aprobat': 'approved',
    'Refuzat': 'rejected',
    'None': 'submitted',
    '': 'submitted',
    None: 'submitted',
}


def name_to_fake_ct_id(name: str) -> int:
    """Generate a deterministic fake Connecteam user ID from a name."""
    h = hashlib.md5(name.strip().upper().encode()).hexdigest()
    return int(h[:12], 16) % 10_000_000_000


def parse_time_str(val) -> str | None:
    """Parse time value from Excel (could be string or datetime)."""
    if val is None:
        return None
    if isinstance(val, time):
        return val.strftime('%H:%M')
    if isinstance(val, datetime):
        return val.strftime('%H:%M')
    s = str(val).strip()
    if not s:
        return None
    # Handle "8:00" -> "08:00"
    if ':' in s:
        parts = s.split(':')
        return f'{int(parts[0]):02d}:{int(parts[1]):02d}'
    return s


def parse_date_val(val) -> date | None:
    """Parse date from Excel (datetime object or string)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def calc_hours(start: str | None, end: str | None) -> float | None:
    """Calculate hours between two HH:MM strings."""
    if not start or not end:
        return None
    try:
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        diff = (eh * 60 + em) - (sh * 60 + sm)
        return round(diff / 60, 2) if diff > 0 else None
    except (ValueError, TypeError):
        return None


def run(xlsx_path: str, db_url: str):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    print(f'Loaded {len(rows)} rows from Excel')

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build JARVIS user lookup by uppercase name
    cur.execute("SELECT id, name FROM users WHERE name IS NOT NULL")
    jarvis_users = {}
    for u in cur.fetchall():
        jarvis_users[u['name'].strip().upper()] = u['id']
    print(f'Loaded {len(jarvis_users)} JARVIS users for name matching')

    # Track stats
    stats = {'users_created': 0, 'users_mapped': 0, 'submissions_inserted': 0,
             'submissions_skipped': 0, 'unmapped_names': set()}

    # Process each row
    for row in rows:
        entry_num = row[0]         # #
        full_name = row[1]         # Full name
        sub_date = row[2]          # Submission Date (datetime)
        # sub_time = row[3]        # Submission Time (string) — redundant
        # department = row[4]      # Departament
        leave_date_val = row[5]    # Data
        start_time = row[6]        # Ora de Plecare
        end_time = row[7]          # Ora de Sosire
        reason = row[8]            # Motive
        # signature = row[9]       # Semnătură Angajat
        approved_by = row[10]      # Aviz superior ierarhic
        # more_recipients = row[11]
        # semnatura = row[12]
        status_raw = row[13]       # Click pentru APROBARE / REFUZ
        # person = row[14]

        if not full_name or not entry_num:
            continue

        name_upper = full_name.strip().upper()
        ct_user_id = name_to_fake_ct_id(full_name)
        submission_id = f'CT-{entry_num}'

        # Skip if already imported
        cur.execute("SELECT 1 FROM connecteam_form_submissions WHERE submission_id = %s",
                    (submission_id,))
        if cur.fetchone():
            stats['submissions_skipped'] += 1
            continue

        # Upsert connecteam_users
        cur.execute("SELECT id, mapped_jarvis_user_id FROM connecteam_users WHERE connecteam_user_id = %s",
                    (ct_user_id,))
        ct_user = cur.fetchone()

        jarvis_uid = jarvis_users.get(name_upper)
        if not jarvis_uid:
            stats['unmapped_names'].add(full_name.strip())

        if not ct_user:
            cur.execute("""
                INSERT INTO connecteam_users
                    (connecteam_user_id, connecteam_user_name, mapped_jarvis_user_id,
                     mapping_method, mapping_confidence, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (connecteam_user_id) DO NOTHING
            """, (ct_user_id, full_name.strip(), jarvis_uid,
                  'name' if jarvis_uid else None,
                  80 if jarvis_uid else 0))
            stats['users_created'] += 1
            if jarvis_uid:
                stats['users_mapped'] += 1
        else:
            jarvis_uid = ct_user['mapped_jarvis_user_id'] or jarvis_uid

        # Parse fields
        leave_date = parse_date_val(leave_date_val)
        start_t = parse_time_str(start_time)
        end_t = parse_time_str(end_time)
        hours = calc_hours(start_t, end_t)
        status = STATUS_MAP.get(str(status_raw).strip() if status_raw else '', 'submitted')

        # Submission timestamp
        if isinstance(sub_date, datetime):
            sub_ts = sub_date
        elif isinstance(sub_date, date):
            sub_ts = datetime.combine(sub_date, time(0, 0))
        else:
            sub_ts = datetime.now()

        # Clean approved_by (take first name if comma-separated)
        approved_str = None
        if approved_by and str(approved_by).strip():
            approved_str = str(approved_by).strip().split(',')[0].strip()

        cur.execute("""
            INSERT INTO connecteam_form_submissions
                (submission_id, form_id, form_name, connecteam_user_id,
                 mapped_jarvis_user_id, submission_timestamp, submission_timezone,
                 entry_num, leave_date, leave_start_time, leave_end_time,
                 leave_hours, leave_reason, approved_by, status,
                 raw_answers, event_type, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            submission_id, FORM_ID, 'Bilet de Invoire', ct_user_id,
            jarvis_uid, sub_ts, 'Europe/Bucharest',
            entry_num, leave_date, start_t, end_t,
            hours, reason, approved_str, status,
            '[]', 'form_submission', sub_ts,
        ))
        stats['submissions_inserted'] += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nImport complete:")
    print(f"  Users created: {stats['users_created']}")
    print(f"  Users mapped to JARVIS: {stats['users_mapped']}")
    print(f"  Submissions inserted: {stats['submissions_inserted']}")
    print(f"  Submissions skipped (duplicate): {stats['submissions_skipped']}")
    if stats['unmapped_names']:
        print(f"  Unmapped names ({len(stats['unmapped_names'])}):")
        for n in sorted(stats['unmapped_names']):
            print(f"    - {n}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python -m scripts.import_connecteam_history <xlsx_path>')
        sys.exit(1)

    xlsx_path = sys.argv[1]
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print('ERROR: DATABASE_URL environment variable is required')
        sys.exit(1)

    if not os.path.exists(xlsx_path):
        print(f'File not found: {xlsx_path}')
        sys.exit(1)

    run(xlsx_path, db_url)
