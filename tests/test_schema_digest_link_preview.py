"""Unit test for the digest schema migration: `digest_posts.link_preview`
column + `digest_link_previews` cache table (chat link-previews feature).
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


def test_schema_adds_link_preview_column_and_cache_table():
    conn, cursor = MagicMock(), MagicMock()
    from migrations.domains.schema_digest import create_schema_digest
    create_schema_digest(conn, cursor)
    sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
    assert "ADD COLUMN IF NOT EXISTS link_preview JSONB" in sql
    assert "CREATE TABLE IF NOT EXISTS digest_link_previews" in sql
    assert "url TEXT PRIMARY KEY" in sql
