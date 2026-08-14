from __future__ import annotations

import pytest

from app.reply_readiness.rate_limit import (
    ReplyDebugRateLimiter,
    ReplyDebugRateLimitExceeded,
)


def test_same_user_and_store_allows_only_one_inflight_request() -> None:
    limiter = ReplyDebugRateLimiter()

    with limiter.acquire("user-1", "store-a"):
        with pytest.raises(ReplyDebugRateLimitExceeded) as blocked:
            with limiter.acquire("user-1", "store-a"):
                pass
        with limiter.acquire("user-1", "store-b"):
            pass
        with limiter.acquire("user-2", "store-a"):
            pass

    assert blocked.value.retry_after_seconds == 1
    with limiter.acquire("user-1", "store-a"):
        pass


def test_attempt_window_is_bounded_and_recovers_after_expiry() -> None:
    now = [100.0]
    limiter = ReplyDebugRateLimiter(
        attempts_per_window=2,
        window_seconds=60,
        clock=lambda: now[0],
    )

    with limiter.acquire("user-1", "store-a"):
        pass
    with limiter.acquire("user-1", "store-a"):
        pass
    with pytest.raises(ReplyDebugRateLimitExceeded) as blocked:
        with limiter.acquire("user-1", "store-a"):
            pass

    assert blocked.value.retry_after_seconds == 60
    now[0] = 160.0
    with limiter.acquire("user-1", "store-a"):
        pass


def test_failed_request_always_releases_inflight_slot() -> None:
    limiter = ReplyDebugRateLimiter()

    with pytest.raises(RuntimeError, match="upstream failed"):
        with limiter.acquire("user-1", "store-a"):
            raise RuntimeError("upstream failed")

    with limiter.acquire("user-1", "store-a"):
        pass
