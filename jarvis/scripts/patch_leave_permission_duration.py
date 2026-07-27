"""Patch script — retrofit the 'Bilet de Invoire' duration field.

The leave-permission form's hours field used to be a decimal-hours number
input labelled "Număr de ore" (e.g. 23:00–23:50 showed "0.83"). It is now a
read-only "Durată" field shown time-wise ("50 min", "2 h 30 min"). The form
already exists in every environment, so the seed skips it — this script patches
the field in place, in both `schema` and `published_schema`. Idempotent.

Usage (targets whatever DATABASE_URL the app is configured with):
    cd jarvis && python -m scripts.patch_leave_permission_duration
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db

FORM_SLUG = 'bilet-de-invoire'
HOURS_FIELD_ID = 'f_bi_hours'

# The field's target shape after the fix.
NEW_FIELD_PATCH = {
    'type': 'text',
    'label': 'Durată',
    'placeholder': '—',
    'config': {
        'duration': {'start': 'f_bi_start_time', 'end': 'f_bi_end_time'},
        'defaultMinutes': 60,
        'hint': 'Se calculează automat din interval.',
    },
}


def _as_list(raw):
    """Schema column may come back as a JSON string or an already-parsed list."""
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


def _patch_schema(schema):
    """Return (patched_schema, changed) with the hours field retrofitted."""
    changed = False
    for field in schema:
        if field.get('id') != HOURS_FIELD_ID:
            continue
        for key, val in NEW_FIELD_PATCH.items():
            if field.get(key) != val:
                field[key] = val
                changed = True
    return schema, changed


def patch():
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        cursor.execute(
            "SELECT id, schema, published_schema FROM forms "
            "WHERE slug = %s AND deleted_at IS NULL",
            (FORM_SLUG,),
        )
        row = cursor.fetchone()
        if not row:
            print(f'Form "{FORM_SLUG}" not found — nothing to patch.')
            return

        def col(r, idx, name):
            return r[idx] if isinstance(r, (list, tuple)) else r[name]

        form_id = col(row, 0, 'id')
        schema = _as_list(col(row, 1, 'schema'))
        published = _as_list(col(row, 2, 'published_schema'))

        schema, changed_a = _patch_schema(schema) if schema else (schema, False)
        published, changed_b = _patch_schema(published) if published else (published, False)

        if not (changed_a or changed_b):
            print(f'Form id={form_id} already patched. Nothing to do.')
            return

        cursor.execute(
            "UPDATE forms SET schema = %s, published_schema = %s WHERE id = %s",
            (json.dumps(schema), json.dumps(published), form_id),
        )
        conn.commit()
        print(f'Patched "Durată" field on form id={form_id} '
              f'(schema={changed_a}, published_schema={changed_b}).')
    except Exception as e:
        conn.rollback()
        print(f'Error patching form: {e}')
        raise
    finally:
        release_db(conn)


if __name__ == '__main__':
    patch()
