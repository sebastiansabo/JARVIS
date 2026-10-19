"""Tests for the Autovit taxonomy map seed (Task 4 of the Autovit Taxonomy
Mapping project). DB-free: `build_seed_rows()` is pure; `seed_map(cursor)` is
exercised against a FakeCursor that just records `execute()` calls,
mirroring `test_autovit_taxonomy_repo.py`'s idiom.
"""
from carpark.connectors.autovit import taxonomy as _taxonomy
from carpark.connectors.autovit.taxonomy_seed import build_seed_rows, seed_map


def _rows_by_key():
    return {(r['dimension'], r['source_value']): r for r in build_seed_rows()}


def test_seed_fuel_benzina_to_petrol():
    rows = _rows_by_key()
    row = rows[('fuel_type', 'benzina')]
    assert row['target_code'] == 'petrol'
    assert row['make'] is None
    assert row['target_code'] == _taxonomy._norm_enum(
        'benzina', _taxonomy._FUEL_SLUGS, _taxonomy._FUEL_ALIASES)


def test_seed_gearbox_automata_to_automatic():
    rows = _rows_by_key()
    row = rows[('gearbox', 'automata')]
    assert row['target_code'] == 'automatic'
    assert row['target_code'] == _taxonomy._norm_enum(
        'automata', _taxonomy._GEARBOX_SLUGS, _taxonomy._GEARBOX_ALIASES)


def test_seed_drive_4x4():
    rows = _rows_by_key()
    row = rows[('drive', '4x4')]
    assert row['target_code'] == _taxonomy._norm_enum(
        '4x4', _taxonomy._DRIVE_SLUGS, _taxonomy._DRIVE_ALIASES)
    assert row['target_code'] == 'all-wheel-permanent'
    assert row['make'] is None


def test_seed_color_reverse_quirk():
    rows = _rows_by_key()
    # 'grey'/'beige' are carpark-canonical SLUGS, not keys of _COLOR_ALIASES
    # — they only show up correctly if the seed walks _COLOR_SLUGS too, not
    # just the RO-label alias keys.
    assert rows[('color', 'grey')]['target_code'] == 'gray'
    assert rows[('color', 'beige')]['target_code'] == 'bej'
    # The RO-label aliases that fold to those same canonical colours must
    # land on the identical final Autovit slug.
    assert rows[('color', 'gri')]['target_code'] == 'gray'
    assert rows[('color', 'bej')]['target_code'] == 'bej'


def test_seed_covers_every_alias_key():
    rows = _rows_by_key()
    tables = {
        'fuel_type': (_taxonomy._FUEL_SLUGS, _taxonomy._FUEL_ALIASES),
        'gearbox': (_taxonomy._GEARBOX_SLUGS, _taxonomy._GEARBOX_ALIASES),
        'drive': (_taxonomy._DRIVE_SLUGS, _taxonomy._DRIVE_ALIASES),
        'body_type': (_taxonomy._BODY_SLUGS, _taxonomy._BODY_ALIASES),
        'pollution_standard': (_taxonomy._EURO_SLUGS, _taxonomy._EURO_ALIASES),
    }
    for dimension, (slugs, aliases) in tables.items():
        for alias_key, expected_target in aliases.items():
            assert (dimension, alias_key) in rows, f'missing seed row for {dimension}:{alias_key}'
            row = rows[(dimension, alias_key)]
            assert row['target_code'] == expected_target == _taxonomy._norm_enum(
                alias_key, slugs, aliases)
            assert row['make'] is None

    # Colour aliases go through the extra _REVERSE step.
    for alias_key in _taxonomy._COLOR_ALIASES:
        assert ('color', alias_key) in rows, f'missing seed row for color:{alias_key}'
        canonical = _taxonomy._norm_enum(
            alias_key, _taxonomy._COLOR_SLUGS, _taxonomy._COLOR_ALIASES, default='other')
        expected = _taxonomy._REVERSE['color'].get(canonical, canonical)
        assert rows[('color', alias_key)]['target_code'] == expected


def test_seed_covers_every_slug_too():
    """Not just aliases: a vehicle whose enum column already stores the
    Autovit-canonical slug directly (e.g. fuel_type='petrol') must still
    resolve — _norm_enum always accepted a bare slug as an identity match,
    so the seed must too, or this is a silent regression for every car that
    already has clean data."""
    rows = _rows_by_key()
    tables = {
        'fuel_type': _taxonomy._FUEL_SLUGS,
        'gearbox': _taxonomy._GEARBOX_SLUGS,
        'drive': _taxonomy._DRIVE_SLUGS,
        'body_type': _taxonomy._BODY_SLUGS,
        'pollution_standard': _taxonomy._EURO_SLUGS,
    }
    for dimension, slugs in tables.items():
        for slug in slugs:
            assert (dimension, slug) in rows, f'missing identity seed row for {dimension}:{slug}'


def test_seed_rows_have_expected_shape():
    for row in build_seed_rows():
        assert set(row.keys()) == {'dimension', 'source_value', 'make', 'target_code', 'target_label'}
        assert row['make'] is None
        assert row['target_code']


def test_seed_map_inserts_each_row_on_conflict_do_nothing():
    calls = []

    class FakeCursor:
        def execute(self, sql, params):
            calls.append((sql, params))

    n = seed_map(FakeCursor())
    rows = build_seed_rows()
    assert n == len(rows)
    assert len(calls) == len(rows)
    sql, params = calls[0]
    assert 'INSERT INTO carpark_autovit_taxonomy_map' in sql
    assert 'ON CONFLICT (dimension, source_value, make) DO NOTHING' in sql
    # params match (dimension, source_value, make, target_code, target_label) order
    seeded = {(r['dimension'], r['source_value']): r for r in rows}
    for sql, params in calls:
        dimension, source_value, make, target_code, target_label = params
        row = seeded[(dimension, source_value)]
        assert make is None
        assert target_code == row['target_code']
        assert target_label == row['target_label']
