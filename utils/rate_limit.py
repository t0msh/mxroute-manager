"""Sliding-window rate limiting backed by SQLite (shared across workers)."""

import time

from models.db_conn import get_conn


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds):
        self.window_seconds = window_seconds

    def _prune(self, cursor, key, now):
        cutoff = now - self.window_seconds
        cursor.execute(
            "DELETE FROM rate_limit_events WHERE bucket_key = ? AND created_at < ?",
            (key, cutoff),
        )

    def _count(self, cursor, key):
        cursor.execute(
            "SELECT COUNT(*) FROM rate_limit_events WHERE bucket_key = ?",
            (key,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def hit(self, key, limit):
        """Record an event and return True if still within `limit`, else False."""
        now = time.time()
        with get_conn() as conn:
            cursor = conn.cursor()
            self._prune(cursor, key, now)
            if self._count(cursor, key) >= limit:
                return False
            cursor.execute(
                "INSERT INTO rate_limit_events (bucket_key, created_at) VALUES (?, ?)",
                (key, now),
            )
            conn.commit()
            return True

    def is_blocked(self, key, limit):
        """Return True if `key` has already reached `limit` within the window."""
        now = time.time()
        with get_conn() as conn:
            cursor = conn.cursor()
            self._prune(cursor, key, now)
            blocked = self._count(cursor, key) >= limit
            conn.commit()
            return blocked

    def register(self, key):
        """Record an event without enforcing a limit (used to count failures)."""
        now = time.time()
        with get_conn() as conn:
            cursor = conn.cursor()
            self._prune(cursor, key, now)
            cursor.execute(
                "INSERT INTO rate_limit_events (bucket_key, created_at) VALUES (?, ?)",
                (key, now),
            )
            conn.commit()

    def retry_after(self, key):
        """Seconds until the oldest recorded event leaves the window (0 if empty)."""
        now = time.time()
        cutoff = now - self.window_seconds
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MIN(created_at) FROM rate_limit_events
                WHERE bucket_key = ? AND created_at >= ?
                """,
                (key, cutoff),
            )
            row = cursor.fetchone()
            oldest = row[0] if row else None
        if oldest is None:
            return 0
        return max(0, int(self.window_seconds - (now - float(oldest))) + 1)

    def clear(self, key=None):
        with get_conn() as conn:
            cursor = conn.cursor()
            if key is None:
                cursor.execute("DELETE FROM rate_limit_events")
            else:
                cursor.execute(
                    "DELETE FROM rate_limit_events WHERE bucket_key = ?",
                    (key,),
                )
            conn.commit()
