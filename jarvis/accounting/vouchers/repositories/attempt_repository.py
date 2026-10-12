"""Rate-limit tracking for voucher code lookup/redeem attempts.

Brute-force / enumeration protection for the code-based voucher endpoints
(``/lookup/<code>``, ``/redeem-by-code`` and their public twins). Mirrors the
``push_rate_limit_log`` pattern: a thin append-only log that the API counts
within a sliding window. Only FAILED attempts are recorded, so a legitimate
redemption never counts toward a limit.
"""
from core.base_repository import BaseRepository


class VoucherAttemptRepository(BaseRepository):
    """Append-only log of voucher code attempts, for rate limiting."""

    def record(self, ip, user_id, voucher_code, outcome='fail'):
        """Record one attempt. Best-effort; the caller swallows errors."""
        self.execute(
            '''INSERT INTO voucher_redeem_attempts (ip, user_id, voucher_code, outcome)
               VALUES (%s, %s, %s, %s)''',
            (ip, user_id, voucher_code, outcome),
        )

    def count_recent(self, *, ip=None, user_id=None, voucher_code=None,
                     window_seconds=600, only_failed=True):
        """Count attempts in the sliding window for exactly ONE key.

        Pass exactly one of ``ip`` / ``user_id`` / ``voucher_code``. When
        ``only_failed`` is True (default) only ``outcome='fail'`` rows count.
        """
        conditions = ["created_at > NOW() - INTERVAL '%s seconds'"]
        params = [window_seconds]
        if ip is not None:
            conditions.append('ip = %s')
            params.append(ip)
        if user_id is not None:
            conditions.append('user_id = %s')
            params.append(user_id)
        if voucher_code is not None:
            conditions.append('voucher_code = %s')
            params.append(voucher_code)
        if only_failed:
            conditions.append("outcome = 'fail'")
        row = self.query_one(
            'SELECT COUNT(*) AS cnt FROM voucher_redeem_attempts WHERE '
            + ' AND '.join(conditions),
            tuple(params),
        )
        return row['cnt'] if row else 0

    def cleanup_old(self, days=7):
        """Delete attempts older than N days (periodic maintenance)."""
        return self.execute(
            "DELETE FROM voucher_redeem_attempts WHERE created_at < NOW() - INTERVAL '%s days'",
            (days,),
        )
