import pytest

from app.services.rate_limit import SlidingWindowRateLimiter


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


async def test_allows_up_to_max_hits_within_window() -> None:
    limiter = SlidingWindowRateLimiter()

    for _ in range(3):
        assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is True


async def test_rejects_hit_beyond_max_within_window() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60)

    assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is False


async def test_allows_again_once_the_window_has_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock(start=1_000.0)
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", clock)
    limiter = SlidingWindowRateLimiter()

    for _ in range(3):
        assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is True
    assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is False

    clock.now += 61
    assert await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60) is True


async def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        await limiter.check("phone:+221771234567", max_hits=3, window_seconds=60)

    assert await limiter.check("phone:+221770000000", max_hits=3, window_seconds=60) is True
    assert await limiter.check("ip:127.0.0.1", max_hits=3, window_seconds=60) is True


async def test_purges_expired_hits_instead_of_accumulating_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock(start=1_000.0)
    monkeypatch.setattr("app.services.rate_limit.time.monotonic", clock)
    limiter = SlidingWindowRateLimiter()
    key = "phone:+221771234567"

    await limiter.check(key, max_hits=3, window_seconds=60)
    await limiter.check(key, max_hits=3, window_seconds=60)
    assert len(limiter._hits[key]) == 2  # noqa: SLF001

    clock.now += 61
    await limiter.check(key, max_hits=3, window_seconds=60)
    # Les 2 hits expirés ont été purgés -- il ne reste que le nouveau.
    assert len(limiter._hits[key]) == 1  # noqa: SLF001
