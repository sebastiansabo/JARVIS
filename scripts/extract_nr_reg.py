"""Extract registration numbers from crm_clients.display_name into nr_reg column.

Patterns:
  - Trade register: J14/48/2012, J40/205/1991 etc.
  - ID card series:  KX 460895, CJ 303903, RT 732361 etc. (2 letters + optional space + 6 digits)
    Excludes RO (CUI/VAT) prefixes.

Also strips the extracted part (and any trailing CNP:...) from display_name to keep names clean.
"""

import re
import psycopg2
import psycopg2.extras

DB_URL = 'postgresql://sebastiansabo@localhost:5432/defaultdb'

# Trade register: J + 1-2 digits + / + digits + / + 4-digit year
TRADE_REG = re.compile(r'\bJ\d{1,2}/\d+/\d{4}\b')

# Romanian ID card: 2 uppercase letters (not RO) + optional space + 6 digits
# Excludes RO (CUI), HRB (German trade register)
ID_CARD = re.compile(r'\b(?!RO|HR)([A-Z]{2})\s?(\d{6})\b')

# CNP pattern (to strip from name): CNP: or CNP followed by 13 digits
CNP_PATTERN = re.compile(r'\s*CNP\s*:?\s*\d{13}')


def extract_nr_reg(name: str) -> tuple[str | None, str]:
    """Return (nr_reg, cleaned_name)."""
    # Try trade register first
    m = TRADE_REG.search(name)
    if m:
        nr_reg = m.group()
        cleaned = name[:m.start()].strip().rstrip()
        # Also remove trailing SRL, SA etc if they got separated
        return nr_reg, cleaned

    # Try ID card
    m = ID_CARD.search(name)
    if m:
        nr_reg = f'{m.group(1)}{m.group(2)}'  # normalize: no space
        cleaned = name[:m.start()].strip()
        # Strip any CNP after the ID card
        cleaned_full = name[:m.start()]
        remainder = name[m.end():]
        remainder = CNP_PATTERN.sub('', remainder).strip()
        cleaned = cleaned_full.strip()
        if remainder:
            cleaned = f'{cleaned} {remainder}'.strip()
        return nr_reg, cleaned

    return None, name


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT id, display_name FROM crm_clients
        WHERE merged_into_id IS NULL AND nr_reg IS NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f'Processing {len(rows)} clients...')

    updated = 0
    name_cleaned = 0
    for row in rows:
        nr_reg, cleaned = extract_nr_reg(row['display_name'])
        if nr_reg:
            # Update nr_reg and clean display_name + name_normalized
            cur.execute("""
                UPDATE crm_clients
                SET nr_reg = %s,
                    display_name = %s,
                    name_normalized = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (nr_reg, cleaned, cleaned.lower().strip(), row['id']))
            updated += 1
            if cleaned != row['display_name']:
                name_cleaned += 1

    conn.commit()
    print(f'Updated {updated} clients with nr_reg')
    print(f'Cleaned {name_cleaned} display names')

    # Stats
    cur.execute("SELECT COUNT(*) FROM crm_clients WHERE nr_reg IS NOT NULL")
    print(f'Total clients with nr_reg: {cur.fetchone()[0]}')
    conn.close()


if __name__ == '__main__':
    main()
