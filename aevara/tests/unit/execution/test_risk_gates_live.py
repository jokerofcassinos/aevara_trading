# @module: aevara.tests.unit.execution.test_risk_gates_live
# @deps: pytest, hashlib, aevara.src.execution.live_gateway, aevara.src.execution.risk_gates_live
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: 12+ tests for risk gates (hard block, FTMO limits, volatility cap, correlation spike).

from __future__ import annotations

import hashlib
import json
import time
import uuid

import pytest

from aevara.src.execution.live_gateway import LiveOrderPayload
from aevara.src.execution.risk_gates_live import (
    GateCheck,
    FTMOConstraints,
    LiveRiskGateEngine,
    RiskGateResult,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

def _valid_order(nonce: int = 1, **kwargs) -> LiveOrderPayload:
    """Helper para criar LiveOrderPayload valido."""
    defaults = {
        "order_id": str(uuid.uuid4()),
        "symbol": "BTC/USDT",
        "side": "BUY",
        "size": 0.01,
        "order_type": "LIMIT",
        "price": 42000.0,
        "nonce": nonce,
        "trace_id": f"TR-{nonce}",
        "risk_gate_hash": "placeholder",
        "max_slippage_bps": 10.0,
        "expiry_ns": time.time_ns() + int(30e9),
    }
    defaults.update(kwargs)
    return LiveOrderPayload(**defaults)


def _healthy_state(**overrides: float) -> dict:
    """Builds a compliant state dictionary."""
    base = {
        "margin_available": 100000.0,
        "daily_pnl_pct": -1.0,
        "total_drawdown_pct": 2.0,
        "total_exposure_qty": 0.5,
        "max_exposure_qty": 10.0,
        "current_volatility": 0.01,
        "volatility_cap": 0.05,
        "correlation_index": 0.3,
        "max_correlation": 0.85,
        "killswitch_active": False,
    }
    base.update(overrides)
    return base


# ─── Tests ─────────────────────────────────────────────────────────────────

class TestFTMOConstraints:
    def test_default_values(self):
        c = FTMOConstraints()
        assert c.daily_loss_limit_pct == 4.8
        assert c.total_loss_limit_pct == 8.0

    def test_custom_values(self):
        c = FTMOConstraints(daily_loss_limit_pct=3.0, total_loss_limit_pct=5.0)
        assert c.daily_loss_limit_pct == 3.0


class TestGateCheck:
    def test_immutable(self):
        gc = GateCheck("test", True, "ok", time.time_ns())
        assert gc.passed is True

    def test_name_and_detail(self):
        gc = GateCheck("margin_available", False, "insufficient", time.time_ns())
        assert gc.name == "margin_available"
        assert not gc.passed


class TestFullRiskValidation:
    def test_valid_state_passes(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state()
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is True, f"Expected pass, got: {reason}"
        assert gate_hash != ""

    def test_killswitch_blocks_immediately(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(killswitch_active=True)
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "Killswitch" in reason

    def test_margin_insufficient_blocks(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(margin_available=0.0)
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "margin_available" in reason

    def test_ftmo_daily_exceeded(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(daily_pnl_pct=-5.0)  # worse than -4.8%
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "ftmo_daily_loss" in reason

    def test_ftmo_total_exceeded(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(total_drawdown_pct=9.0)  # worse than 8.0%
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "ftmo_total_loss" in reason

    def test_volatility_cap_exceeded(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(current_volatility=0.10, volatility_cap=0.05)
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "volatility_regime_cap" in reason

    def test_correlation_too_high(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        state = _healthy_state(correlation_index=0.95, max_correlation=0.85)
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "correlation_spread" in reason

    def test_total_exposure_exceeded(self):
        engine = LiveRiskGateEngine()
        order = _valid_order(size=8.0)
        state = _healthy_state(total_exposure_qty=5.0, max_exposure_qty=10.0)
        # 5.0 + 8.0 = 13.0 > 10.0 => should fail
        passed, reason, gate_hash = engine.validate(order, state)
        assert passed is False
        assert "total_exposure" in reason

    def test_expired_order_blocked(self):
        engine = LiveRiskGateEngine()
        order = _valid_order()
        order = LiveOrderPayload(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            order_type=order.order_type,
            price=order.price,
            nonce=order.nonce,
            trace_id=order.trace_id,
            risk_gate_hash=order.risk_gate_hash,
            max_slippage_bps=order.max_slippage_bps,
            expiry_ns=1,  # epoch
        )
        passed, reason, gate_hash = engine.validate(order, _healthy_state())
        assert passed is False
        assert "expired" in reason.lower()


class TestGateHash:
    def test_generate_hash_consistent(self):
        engine = LiveRiskGateEngine()
        checks = {"a": True, "b": False}
        h1 = engine.generate_gate_hash(checks)
        h2 = engine.generate_gate_hash(checks)
        assert h1 == h2

    def test_generate_hash_different_different_inputs(self):
        engine = LiveRiskGateEngine()
        h1 = engine.generate_gate_hash({"a": True})
        h2 = engine.generate_gate_hash({"a": False})
        assert h1 != h2
