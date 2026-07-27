"""Seed script — Create 'Bilet de Invoire' leave permission form.

Run once on staging/production to create the JARVIS internal form
for leave permission requests. Skips if form already exists.

Usage:
    cd jarvis && python -m scripts.seed_leave_permission_form
"""

import json
import sys
import os

# Add parent dir to path so we can import database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db


FORM_NAME = 'Bilet de Invoire'
FORM_SLUG = 'bilet-de-invoire'
FORM_DESCRIPTION = 'Formular pentru solicitarea unui bilet de invoire (leave permission).'
COMPANY_ID = 16   # AUTOWORLD S.R.L.
OWNER_ID = 1      # Sebastian Sabo

FORM_SCHEMA = [
    {
        'id': 'f_bi_heading',
        'type': 'heading',
        'label': 'Bilet de Invoire',
        'required': False,
        'order': 1,
    },
    {
        'id': 'f_bi_desc',
        'type': 'paragraph',
        'label': 'Completați formularul pentru a solicita un bilet de invoire.',
        'required': False,
        'order': 2,
    },
    {
        'id': 'f_bi_leave_date',
        'type': 'date',
        'label': 'Data',
        'required': True,
        'placeholder': 'Selectați data',
        'order': 3,
    },
    {
        'id': 'f_bi_start_time',
        'type': 'short_text',
        'label': 'Ora de început',
        'required': True,
        'placeholder': 'Ex: 09:00',
        'order': 4,
    },
    {
        'id': 'f_bi_end_time',
        'type': 'short_text',
        'label': 'Ora de sfârșit',
        'required': True,
        'placeholder': 'Ex: 11:00',
        'order': 5,
    },
    {
        'id': 'f_bi_hours',
        'type': 'number',
        'label': 'Număr de ore',
        'required': True,
        'placeholder': 'Ex: 2',
        'order': 6,
        # Auto-computed from the start/end times; editing it shifts the end time.
        'config': {
            'duration': {'start': 'f_bi_start_time', 'end': 'f_bi_end_time'},
            'hint': 'Se calculează automat din interval. Dacă îl editezi, ora de sfârșit se ajustează.',
        },
    },
    {
        'id': 'f_bi_reason',
        'type': 'dropdown',
        'label': 'Motivul',
        'required': True,
        'options': ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul'],
        'order': 7,
    },
    {
        'id': 'f_bi_notes',
        'type': 'long_text',
        'label': 'Detalii suplimentare',
        'required': False,
        'placeholder': 'Adăugați orice detalii relevante',
        'order': 8,
    },
]

FORM_SETTINGS = {
    'thank_you_message': 'Cererea dvs. a fost înregistrată. Veți fi notificat când va fi aprobată.',
    'submission_limit': None,
}


def seed():
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # Check if form already exists
        cursor.execute(
            "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
            (FORM_SLUG,)
        )
        existing = cursor.fetchone()
        if existing:
            form_id = existing[0] if isinstance(existing, (list, tuple)) else existing['id']
            print(f'Form already exists (id={form_id}). Skipping.')
            return form_id

        schema_json = json.dumps(FORM_SCHEMA)
        settings_json = json.dumps(FORM_SETTINGS)

        cursor.execute('''
            INSERT INTO forms
                (name, slug, description, company_id, owner_id, created_by,
                 schema, published_schema, settings, utm_config, branding,
                 requires_approval, status, version, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        ''', (
            FORM_NAME, FORM_SLUG, FORM_DESCRIPTION,
            COMPANY_ID, OWNER_ID, OWNER_ID,
            schema_json, schema_json,  # both schema and published_schema
            settings_json,
            json.dumps({}),   # utm_config
            json.dumps({}),   # branding
            True,             # requires_approval
            'published',      # status — published immediately
            1,                # version
        ))
        form_id = cursor.fetchone()
        form_id = form_id[0] if isinstance(form_id, (list, tuple)) else form_id['id']
        conn.commit()

        print(f'Created and published form "Bilet de Invoire" (id={form_id}, slug={FORM_SLUG})')
        return form_id

    except Exception as e:
        conn.rollback()
        print(f'Error creating form: {e}')
        raise
    finally:
        release_db(conn)


if __name__ == '__main__':
    seed()
