"""Praise repository — two-currency kudos ledger with anti-gaming (spec §7.4).

Giver spends `giveable` (granted monthly, expires); recipient earns `redeemable`
(never expires). Self-award is impossible by schema. Note >= 40 chars and a value
tag are mandatory. Rules 1 (monthly cap) and 4 (duplicate text) BLOCK at submit;
rules 2/3/5 (reciprocity/burst/deadline-dump) FLAG (points still land).
No leaderboards, no points for platform activity — ever.
"""
import json
import logging
from calendar import monthrange
from datetime import timedelta

from core.base_repository import BaseRepository
from happy.services.praise_rules import (
    is_duplicate_note, MIN_NOTE_LEN, MONTHLY_ALLOWANCE, DEFAULT_KUDOS_POINTS,
    MAX_PER_RECIPIENT_PER_MONTH, RECIPROCITY_LIMIT, RECIPROCITY_WINDOW_DAYS,
    BURST_LIMIT, BURST_WINDOW_MIN, DEADLINE_DUMP_PCT,
)

logger = logging.getLogger("jarvis.happy.praise_repository")

_VISIBILITY = ("company", "department", "private")


class KudosError(ValueError):
    """Raised when a kudos is rejected; str(e) is a stable machine code."""


def _period(now):
    return now.strftime("%Y-%m")


def _month_end(now):
    last = monthrange(now.year, now.month)[1]
    return now.replace(day=last, hour=23, minute=59, second=59, microsecond=0)


class PraiseRepository(BaseRepository):

    def list_value_tags(self):
        return self.query_all(
            "SELECT id, slug, label_ro, label_en, icon FROM happy.value_tags "
            "WHERE is_active ORDER BY sort_order, id"
        )

    # -- send -----------------------------------------------------------------

    def send_kudos(self, from_user, to_user, value_tag_id, note, now, points=None,
                   visibility="company"):
        note = (note or "").strip()
        points = points or DEFAULT_KUDOS_POINTS
        if from_user == to_user:
            raise KudosError("self_award")               # also enforced by CHECK
        if len(note) < MIN_NOTE_LEN:
            raise KudosError("note_too_short")
        if not value_tag_id:
            raise KudosError("value_tag_required")
        if points <= 0:
            raise KudosError("invalid_points")
        if visibility not in _VISIBILITY:
            raise KudosError("invalid_visibility")
        period = _period(now)

        def _work(cursor):
            # rule 4 — duplicate text vs giver's last 10 notes (BLOCK)
            cursor.execute(
                "SELECT note FROM happy.kudos WHERE from_user = %s ORDER BY created_at DESC LIMIT 10",
                (from_user,),
            )
            if is_duplicate_note(note, [r["note"] for r in cursor.fetchall()]):
                raise KudosError("duplicate_text")
            # rule 1 — max 3 to same recipient per giver per month (BLOCK)
            cursor.execute(
                "SELECT COUNT(*) c FROM happy.kudos WHERE from_user = %s AND to_user = %s AND period = %s",
                (from_user, to_user, period),
            )
            if cursor.fetchone()["c"] >= MAX_PER_RECIPIENT_PER_MONTH:
                raise KudosError("cap_exceeded")

            _ensure_wallet(cursor, from_user, period)
            # deduct giver (guarded — cannot go negative)
            cursor.execute(
                "UPDATE happy.wallets SET giveable_balance = giveable_balance - %s, updated_at = NOW() "
                "WHERE user_id = %s AND giveable_balance >= %s RETURNING giveable_balance",
                (points, from_user, points),
            )
            if cursor.fetchone() is None:
                raise KudosError("insufficient_giveable")

            cursor.execute(
                """INSERT INTO happy.kudos (from_user, to_user, value_tag_id, note, points, visibility, period)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (from_user, to_user, value_tag_id, note, points, visibility, period),
            )
            kid = cursor.fetchone()["id"]

            # credit recipient (never expires). Ensure the recipient also holds
            # their own monthly giveable first, so a user who only ever received
            # kudos can still give later (a recipient-created wallet must not
            # suppress the monthly grant).
            _ensure_wallet(cursor, to_user, period)
            cursor.execute(
                "UPDATE happy.wallets SET redeemable_balance = redeemable_balance + %s, updated_at = NOW() "
                "WHERE user_id = %s",
                (points, to_user),
            )
            cursor.execute(
                "INSERT INTO happy.point_ledger (user_id, bucket, delta, reason, kudos_id) "
                "VALUES (%s, 'giveable', %s, 'kudos_sent', %s)", (from_user, -points, kid),
            )
            cursor.execute(
                "INSERT INTO happy.point_ledger (user_id, bucket, delta, reason, kudos_id) "
                "VALUES (%s, 'redeemable', %s, 'kudos_received', %s)", (to_user, points, kid),
            )

            flags = _detect_flags(cursor, from_user, to_user, points, now)
            if flags:
                cursor.execute("UPDATE happy.kudos SET flagged = TRUE WHERE id = %s", (kid,))
                for rule, detail in flags:
                    cursor.execute(
                        "INSERT INTO happy.kudos_flags (kudos_id, rule, detail) VALUES (%s, %s, %s::jsonb)",
                        (kid, rule, json.dumps(detail)),
                    )
            return {"id": kid, "points": points, "flagged": bool(flags),
                    "flags": [r for r, _ in flags]}
        return self.execute_many(_work)

    # -- reads ----------------------------------------------------------------

    def get_wallet(self, user_id, now):
        self.execute_many(lambda cur: _ensure_wallet(cur, user_id, _period(now)))
        w = self.query_one(
            "SELECT giveable_balance, giveable_period, redeemable_balance FROM happy.wallets WHERE user_id = %s",
            (user_id,),
        ) or {"giveable_balance": 0, "redeemable_balance": 0, "giveable_period": _period(now)}
        w["giveable_expires_at"] = _month_end(now).isoformat()
        return w

    def get_received(self, user_id, limit=20, offset=0):
        return self.query_all(
            """SELECT k.id, k.from_user, k.note, k.points, k.created_at,
                      vt.slug AS value_tag, vt.label_ro AS value_label
                 FROM happy.kudos k
                 LEFT JOIN happy.value_tags vt ON vt.id = k.value_tag_id
                WHERE k.to_user = %s
                ORDER BY k.created_at DESC LIMIT %s OFFSET %s""",
            (user_id, limit, offset),
        )

    def get_my_praise(self, user_id, now):
        """Own streak + own 12-week trend (given & received). NO peer comparison."""
        cutoff = now - timedelta(weeks=12)
        sent = self.query_all(
            """SELECT to_char(date_trunc('week', created_at), 'IYYY-IW') AS wk, COUNT(*) n
                 FROM happy.kudos WHERE from_user = %s AND created_at >= %s
                 GROUP BY 1 ORDER BY 1""",
            (user_id, cutoff),
        )
        recv = self.query_all(
            """SELECT to_char(date_trunc('week', created_at), 'IYYY-IW') AS wk, COUNT(*) n
                 FROM happy.kudos WHERE to_user = %s AND created_at >= %s
                 GROUP BY 1 ORDER BY 1""",
            (user_id, cutoff),
        )
        sent_weeks = {r["wk"] for r in sent}
        streak = 0
        cursor_ord = now.toordinal()
        while True:
            wk = _iso_week(cursor_ord)
            if wk in sent_weeks:
                streak += 1
                cursor_ord -= 7
            else:
                break
        return {"streak_weeks": streak, "sent": sent, "received": recv}

    def get_flags(self, limit=50):
        return self.query_all(
            """SELECT f.id, f.kudos_id, f.rule, f.detail, f.created_at,
                      k.from_user, k.to_user, k.period
                 FROM happy.kudos_flags f JOIN happy.kudos k ON k.id = f.kudos_id
                ORDER BY f.created_at DESC LIMIT %s""",
            (limit,),
        )


# -- module helpers (operate on the shared execute_many cursor) ---------------

def _iso_week(ordinal):
    import datetime as _dt
    return _dt.date.fromordinal(ordinal).strftime("%G-%V")


def _ensure_wallet(cursor, user_id, period):
    """Grant the monthly allowance on first use / new month; expire old leftover."""
    cursor.execute(
        "SELECT giveable_balance, giveable_period FROM happy.wallets WHERE user_id = %s",
        (user_id,),
    )
    w = cursor.fetchone()
    if w is None:
        cursor.execute(
            "INSERT INTO happy.wallets (user_id, giveable_balance, giveable_period) VALUES (%s, %s, %s)",
            (user_id, MONTHLY_ALLOWANCE, period),
        )
        cursor.execute(
            "INSERT INTO happy.point_ledger (user_id, bucket, delta, reason) VALUES (%s, 'giveable', %s, 'monthly_grant')",
            (user_id, MONTHLY_ALLOWANCE),
        )
    elif w["giveable_period"] != period:
        if w["giveable_balance"]:
            cursor.execute(
                "INSERT INTO happy.point_ledger (user_id, bucket, delta, reason) VALUES (%s, 'giveable', %s, 'expiry')",
                (user_id, -w["giveable_balance"]),
            )
        cursor.execute(
            "UPDATE happy.wallets SET giveable_balance = %s, giveable_period = %s, updated_at = NOW() WHERE user_id = %s",
            (MONTHLY_ALLOWANCE, period, user_id),
        )
        cursor.execute(
            "INSERT INTO happy.point_ledger (user_id, bucket, delta, reason) VALUES (%s, 'giveable', %s, 'monthly_grant')",
            (user_id, MONTHLY_ALLOWANCE),
        )


def _detect_flags(cursor, from_user, to_user, points, now):
    """Non-blocking anti-gaming flags (rules 2/3/5). Points still land."""
    flags = []
    # rule 3 — burst: > BURST_LIMIT from one giver in 60 min
    cursor.execute(
        "SELECT COUNT(*) c FROM happy.kudos WHERE from_user = %s AND created_at >= %s - make_interval(mins => %s)",
        (from_user, now, BURST_WINDOW_MIN),
    )
    if cursor.fetchone()["c"] > BURST_LIMIT:
        flags.append(("burst", {"window_min": BURST_WINDOW_MIN}))
    # rule 2 — reciprocity: A<->B exchanges over limit in 60 days
    cursor.execute(
        """SELECT COUNT(*) c FROM happy.kudos
            WHERE ((from_user = %s AND to_user = %s) OR (from_user = %s AND to_user = %s))
              AND created_at >= %s - make_interval(days => %s)""",
        (from_user, to_user, to_user, from_user, now, RECIPROCITY_WINDOW_DAYS),
    )
    if cursor.fetchone()["c"] > RECIPROCITY_LIMIT:
        flags.append(("reciprocity", {"window_days": RECIPROCITY_WINDOW_DAYS}))
    # rule 5 — deadline-dump: > 50% of allowance spent in the final 48h of the month
    window_start = _month_end(now) - timedelta(hours=48)
    if now >= window_start:
        cursor.execute(
            "SELECT COALESCE(SUM(points), 0) s FROM happy.kudos WHERE from_user = %s AND created_at >= %s",
            (from_user, window_start),
        )
        if cursor.fetchone()["s"] > MONTHLY_ALLOWANCE * DEADLINE_DUMP_PCT:
            flags.append(("deadline_dump", {"pct": DEADLINE_DUMP_PCT}))
    return flags
