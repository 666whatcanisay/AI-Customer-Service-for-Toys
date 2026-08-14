from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass
import math
from threading import Lock
import time
from typing import Callable, Iterator


@dataclass(frozen=True, slots=True)
class ReplyDebugRateLimitExceeded(RuntimeError):
    retry_after_seconds: int


class ReplyDebugRateLimiter:
    """Process-local protection for the single-process LOCAL Admin runtime."""

    def __init__(
        self,
        *,
        attempts_per_window: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if attempts_per_window < 1 or window_seconds <= 0:
            raise ValueError("reply debug rate-limit policy is invalid")
        self.attempts_per_window = attempts_per_window
        self.window_seconds = window_seconds
        self.clock = clock
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._inflight: set[tuple[str, str]] = set()
        self._lock = Lock()

    @contextmanager
    def acquire(self, user_id: str, store_code: str) -> Iterator[None]:
        key = (user_id, store_code)
        now = self.clock()
        with self._lock:
            attempts = self._attempts[key]
            cutoff = now - self.window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if key in self._inflight:
                raise ReplyDebugRateLimitExceeded(retry_after_seconds=1)
            if len(attempts) >= self.attempts_per_window:
                retry_after = max(1, math.ceil(attempts[0] + self.window_seconds - now))
                raise ReplyDebugRateLimitExceeded(
                    retry_after_seconds=retry_after
                )
            attempts.append(now)
            self._inflight.add(key)
        try:
            yield
        finally:
            with self._lock:
                self._inflight.discard(key)
