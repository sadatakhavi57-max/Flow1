"""In-process failed-login limiter - contract section 3 'Brute-force control' (D10). Requires exactly ONE worker process."""
from __future__ import annotations

import math
import threading
from collections import deque

from .errors import DomainError

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60
MAX_KEYS = 100_000


def worker_warning(workers) -> str | None:
    """Startup check: the limiter is per process, so any WORKERS value other than 1 weakens the guarantee."""
    try:
        w = int(workers)
    except (TypeError, ValueError):
        return "WORKERS is not a number; the in-process login limiter requires exactly 1 worker"
    return None if w == 1 else f"WORKERS={w}: the in-process login limiter only guarantees 10 failures / 15 min with exactly 1 worker"


def make_key(organization_code: str, username: str, ip: str | None):
    """Normalized exactly like the login lookup (trim, upper-case organization code, trim + lower-case username)."""
    return (organization_code.strip().upper(), username.strip().lower(), ip or "")


class LoginRateLimiter:
    def __init__(self, clock, max_failures=MAX_FAILURES, window=WINDOW_SECONDS, max_keys=MAX_KEYS):
        self._clock, self._max, self._window, self._max_keys = clock, max_failures, window, max_keys
        self._fails: dict[tuple, deque] = {}
        self._lock = threading.Lock()

    def _prune(self, dq, now):
        while dq and dq[0] <= now - self._window:
            dq.popleft()

    def check(self, key) -> None:
        """Call BEFORE verifying the password (a correct password while locked is still refused). Raises RATE_LIMITED."""
        with self._lock:
            now = self._clock()
            dq = self._fails.get(key)
            if not dq:
                return
            self._prune(dq, now)
            if not dq:
                self._fails.pop(key, None)
                return
            if len(dq) >= self._max:
                retry = max(1, math.ceil(dq[0] + self._window - now))
                raise DomainError("RATE_LIMITED", "Too many failed logins. Try again later.", {"retry_after": retry})

    def record_failure(self, key) -> None:
        """Only real failed attempts are recorded; attempts refused with 429 do not extend the lock."""
        with self._lock:
            now = self._clock()
            if key not in self._fails and len(self._fails) >= self._max_keys:
                self._evict(now)
            dq = self._fails.setdefault(key, deque())
            self._prune(dq, now)
            dq.append(now)

    def _evict(self, now):
        for k in list(self._fails):
            dq = self._fails[k]
            self._prune(dq, now)
            if not dq:
                del self._fails[k]
        if len(self._fails) >= self._max_keys:                 # still full: drop the entry whose newest failure is oldest
            victim = min(self._fails, key=lambda k: self._fails[k][-1])
            del self._fails[victim]

    @staticmethod
    def retry_after(err: DomainError) -> int:
        return int(err.details["retry_after"])
