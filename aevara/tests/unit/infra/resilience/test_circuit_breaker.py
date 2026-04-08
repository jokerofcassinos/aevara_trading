# @module: aevara.tests.unit.infra.resilience.test_circuit_breaker
# @deps: aevara.src.infra.resilience.circuit_breaker
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para CircuitBreaker: state transitions, metrics, recovery, HALF_OPEN probing.

from __future__ import annotations

import asyncio
import time

import pytest

from aevara.src.infra.resilience.circuit_breaker import (
    CBState,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)


async def _async_failing_func():
    raise RuntimeError("boom")


async def _async_special_error():
    class SpecialError(Exception):
        pass
    raise SpecialError("special")


async def _async_success_func():
    return 42


class TestCircuitBreakerTransitions:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_closed_to_open_on_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config=config)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.3)
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN
        await asyncio.sleep(0.4)
        assert cb.state == CBState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success(self):
        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout_s=0.2)
        cb = CircuitBreaker(config=config)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN
        await asyncio.sleep(0.3)
        assert cb.state == CBState.HALF_OPEN
        result = await cb.call(_async_success_func)
        assert result == 42
        assert cb.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.2)
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        await asyncio.sleep(0.3)
        assert cb.state == CBState.HALF_OPEN
        with pytest.raises(RuntimeError):
            await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_reset(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        cb.reset()
        assert cb.state == CBState.CLOSED
        metrics = cb.metrics
        assert metrics["consecutive_failures"] == 0
        assert metrics["half_open_calls"] == 0


# === METRICS ===
class TestCircuitBreakerMetrics:
    @pytest.mark.asyncio
    async def test_metrics_after_calls(self):
        cb = CircuitBreaker()
        await cb.call(_async_success_func)
        await cb.call(_async_success_func)
        metrics = cb.metrics
        assert metrics["calls"] == 2
        assert metrics["successes"] == 2
        assert metrics["failures"] == 0
        assert metrics["state"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_metrics_after_failures(self):
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker(config=config)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        metrics = cb.metrics
        assert metrics["calls"] == 3
        assert metrics["failures"] == 3
        assert metrics["consecutive_failures"] == 3

    @pytest.mark.asyncio
    async def test_history_bounded(self):
        config = CircuitBreakerConfig(failure_threshold=1000)
        cb = CircuitBreaker(config=config)
        for _ in range(600):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        history = cb.get_history()
        assert len(history) <= 500


# === CIRCUIT BREAKER ERROR ===
class TestCircuitBreakerError:
    @pytest.mark.asyncio
    async def test_raises_when_open(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        with pytest.raises(CircuitBreakerError):
            await cb.call(_async_success_func)

    @pytest.mark.asyncio
    async def test_half_open_error_reopens_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout_s=0.2, half_open_max_calls=2)
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN
        await asyncio.sleep(0.3)
        assert cb.state == CBState.HALF_OPEN
        # Failure in HALF_OPEN -> transitions back to OPEN
        with pytest.raises(RuntimeError):
            await cb.call(_async_failing_func)
        assert cb.state == CBState.OPEN


# === MONITORED ERRORS ===
class TestMonitoredErrors:
    @pytest.mark.asyncio
    async def test_only_monitored_errors_trip(self):
        class SpecialError(Exception):
            pass
        config = CircuitBreakerConfig(failure_threshold=2, monitored_errors=(SpecialError,))
        cb = CircuitBreaker(config=config)
        # Non-monitored errors don't trip
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_async_failing_func)
        assert cb.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_monitored_error_trips(self):
        class SpecialError(Exception):
            pass

        async def raise_special():
            raise SpecialError("special")

        config = CircuitBreakerConfig(failure_threshold=2, monitored_errors=(SpecialError,))
        cb = CircuitBreaker(config=config)
        for _ in range(2):
            with pytest.raises(SpecialError):
                await cb.call(raise_special)
        assert cb.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_consecutive_failures_reset_on_success(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config=config)
        await cb.call(_async_success_func)
        with pytest.raises(RuntimeError):
            await cb.call(_async_failing_func)
        with pytest.raises(RuntimeError):
            await cb.call(_async_failing_func)
        await cb.call(_async_success_func)
        assert cb.metrics["consecutive_failures"] == 0
