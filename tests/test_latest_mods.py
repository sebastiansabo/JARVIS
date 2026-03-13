"""Tests for Phase 3+4 tech debt changes and the approval URL hotfix.

Covers:
- AppConfig dataclass (core/config.py)
- Flask app factory (app.py create_app)
- Migration version_manager
- BaseRepository slow query logging
- DropdownRepository in-memory cache
- StructureRepository in-memory cache
- Approval handler APP_BASE_URL env var
- buildQs logic (Python-equivalent for contract verification)
"""
import os
import sys
import time
import logging
import importlib
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ── AppConfig ──────────────────────────────────────────────────────────────

class TestAppConfig:
    def test_from_env_reads_vars(self, monkeypatch):
        monkeypatch.setenv('FLASK_SECRET_KEY', 'mysecret')
        monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/test')
        monkeypatch.setenv('FLASK_ENV', 'production')
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        monkeypatch.setenv('SLOW_QUERY_MS', '500')

        from core.config import AppConfig
        cfg = AppConfig.from_env()

        assert cfg.secret_key == 'mysecret'
        assert cfg.database_url == 'postgresql://localhost/test'
        assert cfg.flask_env == 'production'
        assert cfg.log_level == 'DEBUG'
        assert cfg.slow_query_threshold_ms == 500

    def test_from_env_defaults(self, monkeypatch):
        for v in ('FLASK_SECRET_KEY', 'SECRET_KEY', 'FLASK_ENV', 'LOG_LEVEL', 'SLOW_QUERY_MS'):
            monkeypatch.delenv(v, raising=False)

        from core.config import AppConfig
        cfg = AppConfig.from_env()

        assert cfg.flask_env == 'development'
        assert cfg.log_level == 'INFO'
        assert cfg.slow_query_threshold_ms == 200

    def test_from_env_secret_key_fallback(self, monkeypatch):
        monkeypatch.delenv('FLASK_SECRET_KEY', raising=False)
        monkeypatch.setenv('SECRET_KEY', 'fallbackkey')

        from core.config import AppConfig
        cfg = AppConfig.from_env()
        assert cfg.secret_key == 'fallbackkey'

    def test_validate_raises_without_secret_key(self):
        from core.config import AppConfig
        cfg = AppConfig(secret_key='', database_url='postgresql://x/y')
        with pytest.raises(ValueError, match='FLASK_SECRET_KEY'):
            cfg.validate()

    def test_validate_passes_with_secret_key(self):
        from core.config import AppConfig
        cfg = AppConfig(secret_key='valid', database_url='postgresql://x/y')
        cfg.validate()  # should not raise


# ── Flask app factory ──────────────────────────────────────────────────────

class TestAppFactory:
    def test_create_app_returns_flask_instance(self):
        from flask import Flask
        from core.config import AppConfig
        from app import create_app

        cfg = AppConfig(secret_key='testsecret', database_url=os.environ.get('DATABASE_URL', ''))
        app = create_app(cfg)
        assert isinstance(app, Flask)

    def test_create_app_registers_blueprints(self):
        from core.config import AppConfig
        from app import create_app

        cfg = AppConfig(secret_key='testsecret', database_url=os.environ.get('DATABASE_URL', ''))
        app = create_app(cfg)

        blueprint_names = set(app.blueprints.keys())
        for expected in ('auth', 'organization', 'invoices', 'hr', 'dms', 'crm', 'approvals'):
            assert expected in blueprint_names, f'Blueprint {expected!r} not registered'

    def test_create_app_health_route_exists(self):
        from core.config import AppConfig
        from app import create_app

        cfg = AppConfig(secret_key='testsecret', database_url=os.environ.get('DATABASE_URL', ''))
        app = create_app(cfg)

        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert '/health' in rules

    def test_create_app_sets_secret_key(self):
        from core.config import AppConfig
        from app import create_app

        cfg = AppConfig(secret_key='uniquetestkey123', database_url=os.environ.get('DATABASE_URL', ''))
        app = create_app(cfg)
        assert app.secret_key == 'uniquetestkey123'

    def test_create_app_independent_instances(self):
        """Two calls to create_app with different configs produce independent apps."""
        from core.config import AppConfig
        from app import create_app

        cfg_a = AppConfig(secret_key='keyA', database_url=os.environ.get('DATABASE_URL', ''))
        cfg_b = AppConfig(secret_key='keyB', database_url=os.environ.get('DATABASE_URL', ''))
        app_a = create_app(cfg_a)
        app_b = create_app(cfg_b)

        assert app_a.secret_key == 'keyA'
        assert app_b.secret_key == 'keyB'
        assert app_a is not app_b


# ── Migration version_manager ──────────────────────────────────────────────

class TestVersionManager:
    def _make_cursor(self, fetchone_return=None):
        cursor = MagicMock()
        cursor.fetchone.return_value = fetchone_return
        return cursor

    def test_ensure_version_table_executes_create(self):
        from migrations.version_manager import ensure_version_table
        cursor = self._make_cursor()
        ensure_version_table(cursor)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert 'schema_version' in sql
        assert 'CREATE TABLE IF NOT EXISTS' in sql

    def test_get_schema_version_returns_0_when_empty(self):
        from migrations.version_manager import get_schema_version
        cursor = self._make_cursor(fetchone_return=None)
        assert get_schema_version(cursor) == 0

    def test_get_schema_version_returns_row_value(self):
        from migrations.version_manager import get_schema_version
        cursor = self._make_cursor(fetchone_return=(3,))
        assert get_schema_version(cursor) == 3

    def test_set_schema_version_upserts(self):
        from migrations.version_manager import set_schema_version
        cursor = self._make_cursor()
        set_schema_version(cursor, 5)
        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args[0]
        assert 'ON CONFLICT' in sql
        assert params == (5,)

    def test_run_pending_migrations_updates_when_behind(self):
        from migrations.version_manager import run_pending_migrations, CURRENT_VERSION
        conn = MagicMock()
        cursor = MagicMock()
        # Simulate version 0 in DB
        cursor.fetchone.return_value = None
        run_pending_migrations(conn, cursor)
        # Should have called set_schema_version (upsert with CURRENT_VERSION)
        calls_with_version = [
            c for c in cursor.execute.call_args_list
            if c[0] and 'ON CONFLICT' in c[0][0]
        ]
        assert len(calls_with_version) == 1
        assert calls_with_version[0][0][1] == (CURRENT_VERSION,)

    def test_run_pending_migrations_skips_when_current(self):
        from migrations.version_manager import run_pending_migrations, CURRENT_VERSION
        conn = MagicMock()
        cursor = MagicMock()
        # Simulate DB already at current version
        cursor.fetchone.return_value = (CURRENT_VERSION,)
        run_pending_migrations(conn, cursor)
        # No upsert should have been called
        upsert_calls = [
            c for c in cursor.execute.call_args_list
            if c[0] and 'ON CONFLICT' in c[0][0]
        ]
        assert len(upsert_calls) == 0


# ── BaseRepository slow query logging ─────────────────────────────────────

class TestSlowQueryLogging:
    def test_warn_slow_fires_above_threshold(self):
        # logging_config sets propagate=False, so patch the module logger directly
        import core.base_repository as br
        with patch.object(br._logger, 'warning') as mock_warn:
            br._warn_slow(300, 'SELECT * FROM invoices')
        mock_warn.assert_called_once()
        msg = mock_warn.call_args[0][0]
        assert 'Slow query' in msg
        assert '300' in msg

    def test_warn_slow_silent_below_threshold(self):
        import core.base_repository as br
        with patch.object(br._logger, 'warning') as mock_warn:
            br._warn_slow(50, 'SELECT 1')
        mock_warn.assert_not_called()

    def test_warn_slow_threshold_boundary(self):
        import core.base_repository as br
        with patch.object(br._logger, 'warning') as mock_warn:
            br._warn_slow(br._SLOW_MS, 'SELECT 1')  # exactly at threshold — should NOT fire
        mock_warn.assert_not_called()

    def test_warn_slow_truncates_long_sql(self):
        import core.base_repository as br
        long_sql = 'SELECT ' + 'x' * 200
        with patch.object(br._logger, 'warning') as mock_warn:
            br._warn_slow(500, long_sql)
        mock_warn.assert_called_once()
        msg = mock_warn.call_args[0][0]
        assert 'Slow query' in msg
        # SQL truncated to 120 chars in the log message
        assert long_sql not in msg  # full 207-char SQL should not appear verbatim

    def test_slow_ms_env_var_respected(self, monkeypatch):
        """SLOW_QUERY_MS env var sets the module threshold."""
        monkeypatch.setenv('SLOW_QUERY_MS', '999')
        import core.base_repository as br
        importlib.reload(br)
        assert br._SLOW_MS == 999
        # restore
        monkeypatch.setenv('SLOW_QUERY_MS', '200')
        importlib.reload(br)


# ── DropdownRepository cache ───────────────────────────────────────────────

class TestDropdownCache:
    def setup_method(self):
        # Clear module-level caches before each test
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        dr._options_cache.clear()
        dr._options_all_cache['data'] = None

    def test_get_options_caches_on_second_call(self):
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        repo = dr.DropdownRepository()
        fake_data = [{'id': 1, 'dropdown_type': 'invoice_status', 'value': 'paid', 'label': 'Paid'}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            result1 = repo.get_options('invoice_status')
            result2 = repo.get_options('invoice_status')

        assert result1 == fake_data
        assert result2 == fake_data
        # DB should only be queried once — second call hits cache
        assert mock_q.call_count == 1

    def test_get_options_all_types_cached(self):
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        repo = dr.DropdownRepository()
        fake_data = [{'id': 1, 'dropdown_type': 'invoice_status', 'value': 'paid'}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            result1 = repo.get_options()
            result2 = repo.get_options()

        assert mock_q.call_count == 1
        assert result1 == fake_data

    def test_cache_bypassed_when_active_only(self):
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        repo = dr.DropdownRepository()
        fake_data = [{'id': 1}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            repo.get_options('invoice_status', active_only=True)
            repo.get_options('invoice_status', active_only=True)

        # active_only skips cache — both calls hit DB
        assert mock_q.call_count == 2

    def test_invalidate_clears_type_cache(self):
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        repo = dr.DropdownRepository()
        fake_data = [{'id': 1}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            repo.get_options('invoice_status')
            repo._invalidate_options_cache('invoice_status')
            repo.get_options('invoice_status')

        assert mock_q.call_count == 2  # cache was cleared, so DB queried again

    def test_invalidate_clears_all_cache(self):
        import core.settings.dropdowns.repositories.dropdown_repository as dr
        repo = dr.DropdownRepository()
        fake_data = [{'id': 1}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            repo.get_options()
            repo._invalidate_options_cache()
            repo.get_options()

        assert mock_q.call_count == 2


# ── StructureRepository cache ──────────────────────────────────────────────

class TestStructureCache:
    def setup_method(self):
        import core.organization.repositories.structure_repository as sr
        sr._all_cache['data'] = None

    def test_get_all_caches_on_second_call(self):
        import core.organization.repositories.structure_repository as sr
        repo = sr.StructureRepository()
        fake_data = [{'id': 1, 'company': 'DWA', 'department': 'Marketing'}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            result1 = repo.get_all()
            result2 = repo.get_all()

        assert result1 == fake_data
        assert result2 == fake_data
        assert mock_q.call_count == 1

    def test_invalidate_cache_forces_refetch(self):
        import core.organization.repositories.structure_repository as sr
        repo = sr.StructureRepository()
        fake_data = [{'id': 1}]

        with patch.object(repo, 'query_all', return_value=fake_data) as mock_q:
            repo.get_all()
            repo._invalidate_cache()
            repo.get_all()

        assert mock_q.call_count == 2

    def test_cache_has_ttl(self):
        import core.organization.repositories.structure_repository as sr
        repo = sr.StructureRepository()
        fake_data = [{'id': 1}]

        with patch.object(repo, 'query_all', return_value=fake_data):
            repo.get_all()

        # Cache entry should have a timestamp set
        assert sr._all_cache.get('timestamp') is not None
        assert sr._all_cache.get('ttl') == 300


# ── Approval handler APP_BASE_URL ──────────────────────────────────────────

class TestApprovalHandlerBaseUrl:
    def test_default_base_url_set(self, monkeypatch):
        monkeypatch.delenv('APP_BASE_URL', raising=False)
        import core.approvals.handlers as h
        importlib.reload(h)
        assert h._APP_BASE_URL == 'https://jarvis-mkt-t6fk7.ondigitalocean.app'

    def test_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv('APP_BASE_URL', 'https://staging.example.com')
        import core.approvals.handlers as h
        importlib.reload(h)
        assert h._APP_BASE_URL == 'https://staging.example.com'
        monkeypatch.delenv('APP_BASE_URL', raising=False)
        importlib.reload(h)

    def test_no_hardcoded_old_domain(self):
        """Ensure old mkt-app-922ou domain is not present anywhere in handlers."""
        handlers_path = os.path.join(
            os.path.dirname(__file__), '..', 'jarvis', 'core', 'approvals', 'handlers.py'
        )
        with open(handlers_path) as f:
            content = f.read()
        assert 'mkt-app-922ou' not in content, 'Old hardcoded domain still present in handlers.py'


# ── buildQs contract (Python equivalent) ──────────────────────────────────

class TestBuildQsContract:
    """Verify the logic contract of buildQs (mirrors the TypeScript implementation)."""

    def _build_qs(self, params: dict) -> str:
        """Python replica of the TypeScript buildQs for contract testing."""
        from urllib.parse import urlencode
        filtered = {k: str(v) for k, v in params.items()
                    if v is not None and v != '' and v is not None}
        s = urlencode(filtered)
        return f'?{s}' if s else ''

    def test_empty_params_returns_empty_string(self):
        assert self._build_qs({}) == ''

    def test_skips_none_values(self):
        result = self._build_qs({'page': 1, 'q': None})
        assert 'q' not in result
        assert 'page=1' in result

    def test_skips_empty_string_values(self):
        result = self._build_qs({'status': 'active', 'q': ''})
        assert 'q' not in result
        assert 'status=active' in result

    def test_includes_valid_values(self):
        result = self._build_qs({'page': 1, 'status': 'active'})
        assert result.startswith('?')
        assert 'page=1' in result
        assert 'status=active' in result

    def test_zero_is_included(self):
        # 0 is falsy in Python/JS but should NOT be filtered
        result = self._build_qs({'page': 0})
        assert 'page=0' in result

    def test_false_becomes_string(self):
        result = self._build_qs({'active': False})
        assert 'active=False' in result
