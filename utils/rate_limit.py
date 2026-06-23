"""In-memory sliding-window rate limiting.

ponytail: per-process state with a global lock. Ceiling: limits are enforced per
Gunicorn worker (no cross-worker coordination), and memory grows with the number
of distinct keys until they age out of the window. Upgrade path is a shared store
(e.g. Redis) if strict global limits or many keys are needed.
"""

import time
from collections import defaultdict
from threading import Lock


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds):
        self.window_seconds = window_seconds
        self.buckets = defaultdict(list)
        self.lock = Lock()

    def _prune(self, timestamps, now):
        timestamps[:] = [ts for ts in timestamps if now - ts < self.window_seconds]

    def hit(self, key, limit):
        """Record an event and return True if still within `limit`, else False."""
        now = time.time()
        with self.lock:
            timestamps = self.buckets[key]
            self._prune(timestamps, now)
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            return True

    def is_blocked(self, key, limit):
        """Return True if `key` has already reached `limit` within the window."""
        now = time.time()
        with self.lock:
            timestamps = self.buckets[key]
            self._prune(timestamps, now)
            return len(timestamps) >= limit

    def register(self, key):
        """Record an event without enforcing a limit (used to count failures)."""
        now = time.time()
        with self.lock:
            timestamps = self.buckets[key]
            self._prune(timestamps, now)
            timestamps.append(now)

    def retry_after(self, key):
        """Seconds until the oldest recorded event leaves the window (0 if empty)."""
        now = time.time()
        with self.lock:
            timestamps = self.buckets[key]
            self._prune(timestamps, now)
            if not timestamps:
                return 0
            return max(0, int(self.window_seconds - (now - timestamps[0])) + 1)

    def clear(self, key=None):
        with self.lock:
            if key is None:
                self.buckets.clear()
            else:
                self.buckets.pop(key, None)
