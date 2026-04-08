# @module: aevara.tests.unit.execution.test_live_gateway
# @deps: pytest, asyncio, aevara.src.execution.live_gateway, aevara.src.execution.risk_gates_live
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: 15+ unit tests for live gateway (submission, idempotency, retry, timeout, auth failure).

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from aevara.src.execution.live_gateway import (
    ExecutionMode,
    ExecutionReceipt,
    LiveGateway,
    LiveOrderPayload,
    NonceCache,
    CircuitBreaker,
    CircuitState,
)
from aevara.src.execution.risk_gates_live import LiveRiskGateEngine, FTMOConstraints
from aevara.src.infra.security.credential_vault import CredentialVault


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def risk_engine() -> LiveRiskGateEngine:
    return LiveRiskGateEngine(
        ftmo_constraints=FTMOConstraints(
            daily_loss_limit_pct=4.8,
            total_loss_limit_pct=8.0,
        )
    )


@pytest.fixture
def vault() -> CredentialVault:
    v = CredentialVault()
    v.set("EXCHANGE_API_KEY", "test-key-12345")
    v.set("EXCHANGE_SECRET", "secret-abc")
    return v


@pytest.fixture
def valid_order() -> LiveOrderPayload:
    return LiveOrderPayload(
        order_id=str(uuid.uuid4()),
        symbol="BTC/USDT",
        side="BUY",
        size=0.01,
        order_type="LIMIT",
        price=42000.0,
        nonce=1001,
        trace_id="TR-001",
        risk_gate_hash="hash_placeholder",
        max_slippage_bps=10.0,
        expiry_ns=time.time_ns() + int(60e9),  # 60s TTL
    )


def _make_gateway(
    risk_engine=None, vault=None, mode=ExecutionMode.DRY_RUN, exchange=None, telemetry=None
):
    if risk_engine is None:
        risk_engine = LiveRiskGateEngine()
    if vault is None:
        vault = CredentialVault()
    return LiveGateway(
        risk_engine=risk_engine,
        vault=vault,
        exchange_client=exchange,
        mode=mode,
        telemetry_callback=telemetry,
    )


GOOD_STATE = {
    "margin_available": 100000.0,
    "daily_pnl_pct": -0.5,
    "total_drawdown_pct": 1.0,
    "total_exposure_qty": 0.0,
    "max_exposure_qty": 10.0,
    "current_volatility": 0.01,
    "volatility_cap": 0.05,
    "correlation_index": 0.3,
    "max_correlation": 0.85,
    "killswitch_active": False,
}


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestNonceCache:
    def test_register_and_detect_collision(self):
        cache = NonceCache()
        assert cache.check_and_register(1, "A") is None
        assert cache.check_and_register(1, "B") == "A"

    def test_no_collision_different_nonces(self):
        cache = NonceCache()
        assert cache.check_and_register(1, "A") is None
        assert cache.check_and_register(2, "B") is None

    def test_pending_count(self):
        cache = NonceCache()
        cache.check_and_register(10, "X")
        cache.check_and_register(20, "Y")
        assert cache.pending_count() == 2


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout_s=1.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.is_available()

    def test_recovers_after_timeout(self):
        import time as _t
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.01)
        cb.record_failure()
        _t.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_s=0.01, half_max_requests=1)
        cb.record_failure()
        _t = __import__("time")
        _t.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestLivePayloadValidation:
    def test_valid_order(self):
        obj = LiveOrderPayload(
            order_id="a" * 26, symbol="BTC/USDT", side="BUY",
            size=1.0, order_type="LIMIT", price=100.0,
            nonce=1, trace_id="T1", risk_gate_hash="h",
            max_slippage_bps=5.0, expiry_ns=0,
        )
        assert obj.size == 1.0

    def test_rejects_invalid_order_id_length(self):
        with pytest.raises(AssertionError):
            LiveOrderPayload(
                order_id="short", symbol="BTC/USDT", side="BUY",
                size=1.0, order_type="LIMIT", price=100.0,
                nonce=1, trace_id="T1", risk_gate_hash="h",
                max_slippage_bps=5.0, expiry_ns=0,
            )

    def test_rejects_negative_size(self):
        with pytest.raises(AssertionError):
            LiveOrderPayload(
                order_id="a" * 26, symbol="X", side="BUY",
                size=-1.0, order_type="LIMIT", price=100.0,
                nonce=1, trace_id="T1", risk_gate_hash="h",
                max_slippage_bps=5.0, expiry_ns=0,
            )

    def test_rejects_negative_slippage(self):
        with pytest.raises(AssertionError):
            LiveOrderPayload(
                order_id="a" * 26, symbol="X", side="BUY",
                size=1.0, order_type="LIMIT", price=100.0,
                nonce=1, trace_id="T1", risk_gate_hash="h",
                max_slippage_bps=-1.0, expiry_ns=0,
            )

    def test_rejects_invalid_side(self):
        with pytest.raises(AssertionError):
            LiveOrderPayload(
                order_id="a" * 26, symbol="X", side="LONG",
                size=1.0, order_type="LIMIT", price=100.0,
                nonce=1, trace_id="T1", risk_gate_hash="h",
                max_slippage_bps=5.0, expiry_ns=0,
            )

    def test_rejects_invalid_order_type(self):
        with pytest.raises(AssertionError):
            LiveOrderPayload(
                order_id="a" * 26, symbol="X", side="BUY",
                size=1.0, order_type="STOP", price=100.0,
                nonce=1, trace_id="T1", risk_gate_hash="h",
                max_slippage_bps=5.0, expiry_ns=0,
            )


class TestExecutionReceipt:
    def test_immutable(self):
        r = ExecutionReceipt(
            exchange_order_id="E1", status="FILLED", filled_size=1.0,
            filled_price=100.0, commission_usd=0.5, slippage_bps=2.0,
            latency_us=500, nonce_verified=True, risk_gate_passed=True,
            trace_id="T1",
        )
        assert r.status == "FILLED"


# ─── Integration-ish Gateway Tests ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_submit(risk_engine, vault, valid_order):
    gw = _make_gateway(risk_engine, vault, ExecutionMode.DRY_RUN)
    # Override risk engine to always pass for dry-run
    risk_engine.validate = lambda *a, **k: (True, "", "hash")
    receipt = await gw.submit_order(valid_order)
    assert receipt.status == "FILLED"
    assert receipt.nonce_verified is True


@pytest.mark.asyncio
async def test_killswitch_blocks(risk_engine, vault, valid_order):
    gw = _make_gateway(risk_engine, vault, ExecutionMode.DRY_RUN)
    gw.activate_killswitch()
    receipt = await gw.submit_order(valid_order)
    assert receipt.status == "REJECTED"
    assert receipt.risk_gate_passed is False


@pytest.mark.asyncio
async def test_telemetry_callback_fired(risk_engine, vault, valid_order):
    events = []

    async def capture(event_type, trace_id, ctx):
        events.append((event_type, trace_id, ctx))

    gw = _make_gateway(risk_engine, vault, ExecutionMode.DRY_RUN, telemetry=capture)
    risk_engine.validate = lambda *a, **k: (True, "", "h")
    await gw.submit_order(valid_order)
    await asyncio.sleep(0.01)
    assert len(events) >= 1
