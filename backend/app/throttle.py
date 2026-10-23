"""Failed-login throttling, keyed by email.

Keyed by email rather than IP: behind the reverse proxies every request arrives from the proxy's address.
RedisLoginThrottle shares the count between all API processes; MemoryLoginThrottle keeps it per process
(tests, or running without Redis).
"""

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


class MemoryLoginThrottle:
    # Above this many tracked emails, expired entries are dropped so memory stays bounded.
    PRUNE_THRESHOLD = 10_000

    def __init__(self, max_failures: int, window_seconds: int, now: Callable[[], float] = time.monotonic):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._now = now
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may try again, or None if it isn't blocked."""
        with self._lock:
            now = self._now()
            failures = self._recent(key, now)
            if failures is None or len(failures) < self.max_failures:
                return None
            return max(1, math.ceil(failures[0] + self.window_seconds - now))

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._now()
            if len(self._failures) >= self.PRUNE_THRESHOLD:
                for k in list(self._failures):
                    self._recent(k, now)
            self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()

    def _recent(self, key: str, now: float) -> deque[float] | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        while failures and failures[0] <= now - self.window_seconds:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures


class RedisLoginThrottle:
    """Fixed window starting at the first failure. If Redis is unreachable, logins are not throttled."""

    def __init__(self, client: Redis, max_failures: int, window_seconds: int, prefix: str = "login-failures:"):
        self.client = client
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.prefix = prefix

    def retry_after(self, key: str) -> int | None:
        name = self.prefix + key
        try:
            count, ttl = self.client.pipeline().get(name).ttl(name).execute()
            if count is None or int(count) < self.max_failures:
                return None
            if ttl < 0:
                self.client.expire(name, self.window_seconds)
                ttl = self.window_seconds
            return max(1, ttl)
        except RedisError:
            log.warning("Login throttle unavailable (Redis error); not throttling", exc_info=True)
            return None

    def record_failure(self, key: str) -> None:
        name = self.prefix + key
        try:
            self.client.pipeline().incr(name).expire(name, self.window_seconds, nx=True).execute()
        except RedisError:
            log.warning("Login throttle unavailable (Redis error); failure not recorded", exc_info=True)

    def reset(self, key: str) -> None:
        try:
            self.client.delete(self.prefix + key)
        except RedisError:
            log.warning("Login throttle unavailable (Redis error); reset skipped", exc_info=True)

    def clear(self) -> None:
        try:
            for name in self.client.scan_iter(match=self.prefix + "*"):
                self.client.delete(name)
        except RedisError:
            log.warning("Login throttle unavailable (Redis error); clear skipped", exc_info=True)
