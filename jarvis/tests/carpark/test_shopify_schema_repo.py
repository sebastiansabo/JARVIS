# jarvis/tests/carpark/test_shopify_schema_repo.py
from carpark.connectors.shopify.schema_repository import SchemaRepository
from carpark.connectors.shopify import translations


def test_get_field_map_returns_rows(monkeypatch):
    rows = [
        {'id': 1, 'source_expr': 'marca', 'target_namespace': 'custom', 'target_key': 'marca',
         'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': True},
    ]
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: rows)
    assert repo.get_field_map() == rows


def test_get_active_field_map_filters_active_and_seen(monkeypatch):
    calls = []

    def fake_query_all(sql, params=None):
        calls.append(sql)
        return []

    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', fake_query_all)
    repo.get_active_field_map()
    assert len(calls) == 1
    sql = calls[0].lower()
    assert 'is_active' in sql
    assert 'last_seen_in_store' in sql


def test_upsert_field_coerces_none_source_expr_to_empty_string(monkeypatch):
    # source_expr is NOT NULL in the DB; a client omitting it must not 500.
    execute_calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'execute', lambda sql, params=None: execute_calls.append(params))

    repo.upsert_field(None, 'custom', 'marca', 'single_line_text_field', 'raw')

    assert len(execute_calls) == 1
    assert execute_calls[0][0] == ''


def test_get_value_map_groups_by_dimension(monkeypatch):
    rows = [
        {'dimension': 'fuel_type', 'source_value': 'Motorină', 'ro_value': 'Diesel'},
        {'dimension': 'fuel_type', 'source_value': 'Benzină', 'ro_value': 'Petrol'},
        {'dimension': 'color', 'source_value': 'Negru', 'ro_value': 'Black'},
    ]
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: rows)
    m = repo.get_value_map()
    assert m == {
        'fuel_type': {'Motorină': 'Diesel', 'Benzină': 'Petrol'},
        'color': {'Negru': 'Black'},
    }


def _field_map_rows():
    return [
        {'id': 1, 'source_expr': 'marca', 'target_namespace': 'custom', 'target_key': 'marca',
         'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': True},
        {'id': 2, 'source_expr': 'dropped_expr', 'target_namespace': 'custom', 'target_key': 'dropped',
         'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': True},
        {'id': 3, 'source_expr': 'model', 'target_namespace': 'custom', 'target_key': 'model',
         'target_type': 'number', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': True},
    ]


def test_reconcile_returns_new_stale_type_changed_ok(monkeypatch):
    store_defs = {
        'custom.marca': 'single_line_text_field',
        'custom.model': 'single_line_text_field',  # map has 'number' -> type_changed
        'custom.new_field': 'boolean',              # not in map -> new
        # 'custom.dropped' intentionally absent -> stale
    }

    execute_calls = []

    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: _field_map_rows())
    monkeypatch.setattr(repo, 'execute', lambda sql, params=None: execute_calls.append((sql, params)))

    result = repo.reconcile(store_defs)

    assert result['new'] == [{'namespace': 'custom', 'key': 'new_field', 'type': 'boolean'}]
    assert result['stale'] == [{'target_namespace': 'custom', 'target_key': 'dropped'}]
    assert result['type_changed'] == [{
        'target_namespace': 'custom', 'target_key': 'model',
        'map_type': 'number', 'store_type': 'single_line_text_field',
    }]
    assert result['ok'] == 1

    # Only the 'dropped' row changed seen-state (True -> False); marca/model stayed seen=True.
    assert len(execute_calls) == 1
    sql, params = execute_calls[0]
    assert 'last_seen_in_store' in sql.lower()
    assert params == (False, 'custom', 'dropped')


def test_reconcile_marks_reappeared_row_as_seen_again(monkeypatch):
    rows = [
        {'id': 1, 'source_expr': 'marca', 'target_namespace': 'custom', 'target_key': 'marca',
         'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': False},
    ]
    store_defs = {'custom.marca': 'single_line_text_field'}

    execute_calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: rows)
    monkeypatch.setattr(repo, 'execute', lambda sql, params=None: execute_calls.append((sql, params)))

    result = repo.reconcile(store_defs)

    assert result['ok'] == 1
    assert result['stale'] == []
    assert len(execute_calls) == 1
    sql, params = execute_calls[0]
    assert params == (True, 'custom', 'marca')


def test_reconcile_persist_false_makes_no_execute(monkeypatch):
    # Same stale-row setup as test_reconcile_marks_reappeared_row_as_seen_again's
    # sibling above, but with a row that WILL flip seen-state (in_store != was_seen)
    # so a persist=True call would issue an UPDATE — persist=False must suppress it.
    rows = [
        {'id': 1, 'source_expr': 'marca', 'target_namespace': 'custom', 'target_key': 'marca',
         'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True,
         'last_seen_in_store': True},
    ]
    store_defs: dict = {}  # 'custom.marca' now absent -> stale, seen-state flips True->False

    execute_calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'query_all', lambda *a, **k: rows)
    monkeypatch.setattr(repo, 'execute', lambda sql, params=None: execute_calls.append((sql, params)))

    result = repo.reconcile(store_defs, persist=False)

    assert result['stale'] == [{'target_namespace': 'custom', 'target_key': 'marca'}]
    assert execute_calls == []


def test_ensure_defaults_backfills_all_entries_do_nothing(monkeypatch):
    # ensure_defaults() upserts EVERY default field + value with ON CONFLICT DO
    # NOTHING, so missing entries added to the seed after a connector was first
    # seeded (e.g. all-wheel-*/mild-hybrid) get backfilled WITHOUT clobbering
    # existing rows or manual edits. (Replaces seed-only-if-empty, which never
    # backfilled prod.)
    SchemaRepository._defaults_ensured = False
    calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'execute', lambda sql, params=None, **k: calls.append((sql, params)))

    repo.ensure_defaults()

    n_fields = len(translations.DEFAULT_FIELD_MAP)
    n_values = sum(len(m) for m in translations.VALUE_TRANSLATIONS_SEED.values())
    assert len(calls) == n_fields + n_values
    assert all('ON CONFLICT' in sql and 'DO NOTHING' in sql for sql, _ in calls)
    # the previously-missing drive mapping is among the backfilled values
    value_params = [p for sql, p in calls if 'carpark_shopify_value_map' in sql]
    assert ('drive_type', 'all-wheel-auto', 'Integrală') in [(p[0], p[1], p[2]) for p in value_params]


def test_ensure_defaults_runs_once_per_process(monkeypatch):
    SchemaRepository._defaults_ensured = False
    calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'execute', lambda *a, **k: calls.append(1))
    repo.ensure_defaults()
    first = len(calls)
    assert first > 0
    repo.ensure_defaults()  # gated — no further inserts this process
    assert len(calls) == first


def test_seed_defaults_if_empty_is_backfill_alias(monkeypatch):
    SchemaRepository._defaults_ensured = False
    calls = []
    repo = SchemaRepository()
    monkeypatch.setattr(repo, 'execute', lambda *a, **k: calls.append(1))
    repo.seed_defaults_if_empty()  # back-compat alias → ensure_defaults
    assert len(calls) > 0
