# @module: aevara.tests.unit.infra.network.test_rate_limiter
# @deps: aevara.src.infra.network.rate_limiter
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para SlidingWindowRateLimiter: acquire, backoff, per-endpoint, burst, pruning.

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio

from aevara.src.infra.network.rate_limiter import RateLimitConfig, SlidingWindowRateLimiter


async def _acquire_many(limiter, endpoint, count):
    results = []
    for _ in range(count):
        results.append(await limiter.acquire(endpoint))
    return results


async def _acquire_one(limiter, endpoint):
    return await limiter.acquire(endpoint)


# === BACKOFF ===
class TestRateLimiterBackoff:
    def test_backoff_increases_with_attempt(self):
        config = RateLimitConfig(max_requests=60, window_s=60.0, backoff_base_ms=100, backoff_max_ms=30000, jitter_factor=0.0)
        b0 = SlidingWindowRateLimiter.compute_backoff(0, config)
        b1 = SlidingWindowRateLimiter.compute_backoff(1, config)
        b2 = SlidingWindowRateLimiter.compute_backoff(2, config)
        assert b0 < b1 < b2

    def test_backoff_clamped_at_max(self):
        config = RateLimitConfig(max_requests=60, window_s=60.0, backoff_base_ms=100, backoff_max_ms=1000, jitter_factor=0.0)
        b = SlidingWindowRateLimiter.compute_backoff(10, config)
        assert b <= config.backoff_max_ms / 1000.0

    def test_backoff_jitter_range(self):
        config = RateLimitConfig(max_requests=60, window_s=60.0, backoff_base_ms=1000, backoff_max_ms=30000, jitter_factor=0.25)
        for _ in range(50):
            b = SlidingWindowRateLimiter.compute_backoff(0, config)
            assert 0.75 <= b <= 1.25

    def test_backoff_zero_jitter_deterministic(self):
        config = RateLimitConfig(max_requests=60, window_s=60.0, backoff_base_ms=500, backoff_max_ms=10000, jitter_factor=0.0)
        results = [SlidingWindowRateLimiter.compute_backoff(3, config) for _ in range(5)]
        assert all(r == results[0] for r in results)


# === ASYNC ACQUIRE ===
class TestRateLimiterAcquire:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        config = RateLimitConfig(max_requests=3, window_s=10.0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        allowed1, _ = await _acquire_one(limiter, "/api/test")
        allowed2, _ = await _acquire_one(limiter, "/api/test")
        allowed3, _ = await _acquire_one(limiter, "/api/test")
        assert allowed1
        assert allowed2
        assert allowed3

    @pytest.mark.asyncio
    async def test_acquire_denied_over_limit(self):
        config = RateLimitConfig(max_requests=2, window_s=10.0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        await _acquire_many(limiter, "/api/test", 2)
        allowed, wait = await _acquire_one(limiter, "/api/test")
        assert not allowed
        assert wait > 0

    @pytest.mark.asyncio
    async def test_burst_allowance(self):
        config = RateLimitConfig(max_requests=2, window_s=10.0, burst_allowance=3)
        limiter = SlidingWindowRateLimiter(default_config=config)
        results = await _acquire_many(limiter, "/api/test", 5)
        for i, (allowed, _) in enumerate(results):
            assert allowed, f"Request {i+1} should be allowed with burst"
        allowed, wait = await _acquire_one(limiter, "/api/test")
        assert not allowed
        assert wait > 0

    @pytest.mark.asyncio
    async def test_window_resets_after_timeout(self):
        config = RateLimitConfig(max_requests=2, window_s=0.5)
        limiter = SlidingWindowRateLimiter(default_config=config)
        await _acquire_many(limiter, "/api/test", 2)
        allowed, _ = await _acquire_one(limiter, "/api/test")
        assert not allowed
        await asyncio.sleep(0.6)
        allowed, _ = await _acquire_one(limiter, "/api/test")
        assert allowed

    @pytest.mark.asyncio
    async def test_remaining_count(self):
        config = RateLimitConfig(max_requests=3, window_s=10.0, burst_allowance=0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        assert limiter.get_remaining("/api/test") == 3
        await _acquire_one(limiter, "/api/test")
        assert limiter.get_remaining("/api/test") == 2

    @pytest.mark.asyncio
    async def test_remaining_respects_window(self):
        config = RateLimitConfig(max_requests=3, window_s=0.3, burst_allowance=0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        await _acquire_many(limiter, "/api/test", 3)
        assert limiter.get_remaining("/api/test") == 0
        await asyncio.sleep(0.4)
        assert limiter.get_remaining("/api/test") == 3


# === ENDPOINT CONFIGURATION ===
class TestRateLimiterEndpoints:
    @pytest.mark.asyncio
    async def test_configure_endpoint(self):
        limiter = SlidingWindowRateLimiter()
        custom = RateLimitConfig(max_requests=100, window_s=60.0)
        limiter.configure_endpoint("/api/premium", custom)
        for _ in range(100):
            allowed, _ = await limiter.acquire("/api/premium")
            assert allowed

    @pytest.mark.asyncio
    async def test_unknown_endpoint_uses_default(self):
        config = RateLimitConfig(max_requests=1, window_s=10.0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        allowed1, _ = await limiter.acquire("/unknown")
        assert allowed1
        allowed2, _ = await limiter.acquire("/unknown")
        assert not allowed2

    @pytest.mark.asyncio
    async def test_multiple_endpoints_independent(self):
        config = RateLimitConfig(max_requests=1, window_s=10.0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        await limiter.acquire("/api/a")
        await limiter.acquire("/api/b")
        assert limiter.get_remaining("/api/a") == 0
        assert limiter.get_remaining("/api/b") == 0

    def test_prune_window(self):
        limiter = SlidingWindowRateLimiter()
        from collections import deque
        window = deque()
        now = time.monotonic()
        window.append(now - 10.0)
        window.append(now - 5.0)
        window.append(now - 0.5)
        limiter._prune_window(window, 2.0)
        assert len(window) == 1
        assert window[0] > now - 2.0

    def test_reset_endpoint(self):
        config = RateLimitConfig(max_requests=1, window_s=10.0)
        limiter = SlidingWindowRateLimiter(default_config=config)
        limiter._get_window("/api/test").append(time.monotonic())
        assert limiter.get_remaining("/api/test") == 0
        limiter.reset("/api/test")
        assert limiter.get_remaining("/api/test") == 1

    def test_get_all_endpoints(self):
        limiter = SlidingWindowRateLimiter()
        limiter._get_window("/api/a").append(time.monotonic())
        limiter._get_window("/api/b").append(time.monotonic())
        endpoints = limiter.get_all_endpoints()
        assert set(endpoints) == {"/api/a", "/api/b"}
