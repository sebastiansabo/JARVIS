"""Real-DB tests for the hr.event_bonus_days table, view, and backfill.

Run against localhost/defaultdb; skipped when no real Postgres is reachable.
"""
from .conftest import make_bonus


def test_table_and_columns_exist(hr_ctx):
    conn, cur, ctx = hr_ctx
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'hr' AND table_name = 'event_bonus_days'
    """)
    cols = {r['column_name'] for r in cur.fetchall()}
    assert {'id', 'bonus_id', 'day'} <= cols


def test_unique_bonus_day_constraint(hr_ctx):
    conn, cur, ctx = hr_ctx
    bonus_id = make_bonus(cur, ctx, year=2099, month=2, bonus_net=100, bonus_days=1)
    cur.execute("INSERT INTO hr.event_bonus_days (bonus_id, day) VALUES (%s, '2099-02-01')",
                (bonus_id,))
    conn.commit()
    # second identical (bonus_id, day) must violate the UNIQUE constraint
    import psycopg2
    try:
        cur.execute("INSERT INTO hr.event_bonus_days (bonus_id, day) VALUES (%s, '2099-02-01')",
                    (bonus_id,))
        conn.commit()
        assert False, 'duplicate (bonus_id, day) should have been rejected'
    except psycopg2.errors.UniqueViolation:
        conn.rollback()


def test_days_cascade_delete_with_bonus(hr_ctx):
    conn, cur, ctx = hr_ctx
    bonus_id = make_bonus(cur, ctx, year=2099, month=2, bonus_net=100, bonus_days=1)
    cur.execute("INSERT INTO hr.event_bonus_days (bonus_id, day) VALUES (%s, '2099-02-01')",
                (bonus_id,))
    conn.commit()
    cur.execute("DELETE FROM hr.event_bonuses WHERE id = %s", (bonus_id,))
    conn.commit()
    cur.execute("SELECT count(*) AS n FROM hr.event_bonus_days WHERE bonus_id = %s", (bonus_id,))
    assert cur.fetchone()['n'] == 0


def test_view_splits_day_net_uniformly_across_months(hr_ctx):
    conn, cur, ctx = hr_ctx
    # 2 days, 200 net -> each day carries 100; days straddle the Jan/Feb boundary
    bonus_id = make_bonus(cur, ctx, year=2099, month=1, bonus_net=200, bonus_days=2)
    cur.executemany(
        "INSERT INTO hr.event_bonus_days (bonus_id, day) VALUES (%s, %s)",
        [(bonus_id, '2099-01-31'), (bonus_id, '2099-02-02')])
    conn.commit()
    cur.execute("""
        SELECT year, month, day_net FROM hr.v_event_bonus_days
        WHERE bonus_id = %s ORDER BY day
    """, (bonus_id,))
    rows = cur.fetchall()
    assert [(r['year'], r['month'], float(r['day_net'])) for r in rows] == [
        (2099, 1, 100.0), (2099, 2, 100.0)]


def test_backfill_materializes_consecutive_days_for_legacy_bonus(hr_ctx):
    conn, cur, ctx = hr_ctx
    # legacy row: 4-day window but only 2 bonus_days, no day rows yet
    bonus_id = make_bonus(cur, ctx, year=2099, month=1, bonus_net=100, bonus_days=2,
                          participation_start='2099-01-30', participation_end='2099-02-02')
    conn.commit()
    from migrations.domains.schema_hr import backfill_event_bonus_days
    backfill_event_bonus_days(conn, cur)
    conn.commit()
    cur.execute("SELECT day FROM hr.event_bonus_days WHERE bonus_id = %s ORDER BY day",
                (bonus_id,))
    days = [r['day'].isoformat() for r in cur.fetchall()]
    # round(bonus_days)=2 consecutive days from participation_start
    assert days == ['2099-01-30', '2099-01-31']
