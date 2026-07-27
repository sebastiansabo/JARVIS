"""Patch — add the optional second-approver field to the Bilet de Invoire form.

The form already exists in every environment (seed skips it), so add the field
in place, in both `schema` and `published_schema`. Idempotent.

Usage: cd jarvis && python scripts/patch_leave_permission_second_approver.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db, get_cursor, release_db

FORM_SLUG = 'bilet-de-invoire'
FIELD_ID = 'f_bi_second_approver'
NEW_FIELD = {
    'id': FIELD_ID,
    'type': 'user_select',
    'label': 'Al doilea aprobator (opțional)',
    'required': False,
    'order': 8,
    'config': {'hint': 'Oricare dintre aprobatori poate aproba. Lasă gol pentru aprobare doar de managerul direct.'},
}


def _as_list(raw):
    return None if raw is None else (json.loads(raw) if isinstance(raw, str) else raw)


def _patch(schema):
    if any(f.get('id') == FIELD_ID for f in schema):
        return schema, False
    # Insert before the notes field if present, else append.
    idx = next((i for i, f in enumerate(schema) if f.get('id') == 'f_bi_notes'), len(schema))
    schema.insert(idx, dict(NEW_FIELD))
    return schema, True


def patch():
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        cursor.execute(
            "SELECT id, schema, published_schema FROM forms WHERE slug=%s AND deleted_at IS NULL",
            (FORM_SLUG,),
        )
        row = cursor.fetchone()
        if not row:
            print(f'Form "{FORM_SLUG}" not found — nothing to patch.')
            return

        def col(r, i, n):
            return r[i] if isinstance(r, (list, tuple)) else r[n]

        form_id = col(row, 0, 'id')
        schema, ca = _patch(_as_list(col(row, 1, 'schema')) or [])
        published, cb = _patch(_as_list(col(row, 2, 'published_schema')) or [])
        if not (ca or cb):
            print(f'Form id={form_id} already has {FIELD_ID}. Nothing to do.')
            return
        cursor.execute(
            "UPDATE forms SET schema=%s, published_schema=%s WHERE id=%s",
            (json.dumps(schema), json.dumps(published), form_id),
        )
        conn.commit()
        print(f'Added {FIELD_ID} to form id={form_id} (schema={ca}, published_schema={cb}).')
    except Exception as e:
        conn.rollback()
        print(f'Error: {e}')
        raise
    finally:
        release_db(conn)


if __name__ == '__main__':
    patch()
