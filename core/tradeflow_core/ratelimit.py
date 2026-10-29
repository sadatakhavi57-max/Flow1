"""In-process failed-login limiter - contract section 3 'Brute-force control' (D10).

10 failures per key in 15 minutes -> 429 RATE_LIMITED with Retry-After.  Key = (organization_code, username, client IP),
normalized like login.  The limit is per key, not global.  In-process memory => the deployment must run exactly one worker.
A successful login does NOT reset the counter (the contract is silent; this is the stricter reading).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable

from .digits import normalize_digits
from .errors import AppError, ErrorCode


def normalize_key(org_code: str, username: str, ip: str) -> tuple[str, str, str]:
    return (normalize_digits(org_code.strip()).upper(), username.strip().lower(), ip.strip())


class LoginRateLimiter:
    def __init__(self, max_failures: int = 10, window_seconds: int = 900, max_keys: int = 100_000,
                 clock: Callable[[], float] = time.monotonic):
        self.max_failures, self.window, self.max_keys, self._clock = max_failures, window_seconds, max_keys, clock
        self._events: "OrderedDict[tuple, deque]" = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, key, now):
        q = self._events.get(key)
        if q is None:
            return None
        while q and now - q[0] >= self.window:
            q.popleft()
        if not q:
            del self._events[key]
            return None
        return q

    def check(self, key: tuple) -> None:
        """Call BEFORE verifying the password. Raises RATE_LIMITED (details.retry_after seconds >= 1)."""
        with self._lock:
            now = self._clock()
            q = self._prune(key, now)
            if q is not None and len(q) >= self.max_failures:
                retry = max(1, int(q[0] + self.window - now + 0.999))
                e = AppError(ErrorCode.RATE_LIMITED, details={"retry_after": retry})
                e.retry_after = retry
                raise e

    def record_failure(self, key: tuple) -> None:
        with self._lock:
            now = self._clock()
            q = self._prune(key, now)
            if q is None:
                if len(self._events) >= self.max_keys:          # memory bound: forget the least recently created key
                    self._events.popitem(last=False)
                q = self._events.setdefault(key, deque())
            q.append(now)
