import os, psycopg2, pytest
from psycopg2.extras import RealDictCursor

pytestmark = pytest.mark.skipif(not os.environ.get('DATABASE_URL'), reason='needs real DB')

def _cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r['column_name'] for r in cur.fetchall()}

def test_enhanced_columns_exist():
    from migrations.domains.schema_carpark import create_schema_carpark  # entrypoint: (conn, cursor)
    conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=RealDictCursor)
    cur = conn.cursor()
    create_schema_carpark(conn, cur); conn.commit()
    cols = _cols(cur, 'carpark_vehicle_photos')
    assert {'enhanced_url','enhanced_thumbnail_url','enhanced_background_id',
            'enhanced_published','enhanced_created_at'} <= cols
    conn.close()
