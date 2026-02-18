"""Base Repository — eliminates connection boilerplate across all repos.

Provides query_one(), query_all(), execute(), execute_many() that handle
get_db()/get_cursor()/release_db() and try/finally automatically.

Usage:
    class MyRepo(BaseRepository):
        def get_thing(self, id):
            return self.query_one('SELECT * FROM things WHERE id = %s', (id,))

        def get_all_things(self):
            return self.query_all('SELECT * FROM things ORDER BY name')

        def save_thing(self, name):
            return self.execute(
                'INSERT INTO things (name) VALUES (%s) RETURNING id',
                (name,), returning=True
            )

        def complex_op(self):
            def _work(cursor):
                cursor.execute('UPDATE ...')
                cursor.execute('INSERT ...')
                return cursor.fetchone()
            return self.execute_many(_work)
"""

from database import get_db, get_cursor, release_db, dict_from_row


class BaseRepository:

    def query_one(self, sql, params=None):
        """Execute a SELECT and return a single row as dict, or None."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(sql, params or ())
            row = cursor.fetchone()
            return dict_from_row(row) if row else None
        finally:
            release_db(conn)

    def query_all(self, sql, params=None):
        """Execute a SELECT and return all rows as list of dicts."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(sql, params or ())
            return [dict_from_row(r) for r in cursor.fetchall()]
        finally:
            release_db(conn)

    def execute(self, sql, params=None, returning=False):
        """Execute an INSERT/UPDATE/DELETE with auto-commit.

        Args:
            sql: SQL statement
            params: Query parameters
            returning: If True, fetchone() and return dict. If False, return rowcount.

        Returns:
            dict if returning=True, else int (rowcount)
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(sql, params or ())
            if returning:
                result = cursor.fetchone()
                conn.commit()
                return dict_from_row(result) if result else None
            conn.commit()
            return cursor.rowcount
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def execute_many(self, callback):
        """Execute multiple statements in a single transaction.

        Args:
            callback: Function that receives (cursor) and returns a result.
                      All statements within callback share one connection/transaction.

        Returns:
            Whatever callback returns
        """
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            result = callback(cursor)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)
