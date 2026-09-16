"""Real-DB guard for carpark_vehicles column widths.

drive_type/euro_standard shipped as VARCHAR(10) but must fit Autovit taxonomy
enum values ('all-wheel-permanent' = 19, 'euro-6d-temp' = 12). A pre-existing
prod table stayed VARCHAR(10) because the widening was only applied to
CREATE TABLE (no ALTER), which broke Autovit import with "value too long for
type character varying(10)". _create_carpark_incremental() now widens in place;
this test guards against anything re-narrowing them below what the taxonomy
writes.

Runs against localhost/defaultdb via the probe in conftest.py; skips when no
real DB is available.
"""
import pytest

from .conftest import REAL_DB_AVAILABLE

# column -> minimum width the Autovit taxonomy can write into it
_MIN_WIDTHS = {'drive_type': 19, 'euro_standard': 12}


@pytest.mark.parametrize('column,min_width', sorted(_MIN_WIDTHS.items()))
def test_carpark_vehicles_column_fits_autovit_enums(column, min_width):
    if not REAL_DB_AVAILABLE:
        pytest.skip('requires localhost/defaultdb')
    from database import get_db, release_db
    from psycopg2.extras import RealDictCursor
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT character_maximum_length
                   FROM information_schema.columns
                   WHERE table_name='carpark_vehicles' AND column_name=%s""",
                (column,),
            )
            row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, f'{column} missing from carpark_vehicles'
    width = row['character_maximum_length']
    assert width >= min_width, (
        f'{column} is VARCHAR({width}); Autovit writes up to {min_width} chars '
        f'— import will fail with "value too long". Run the widening migration.'
    )
