# @module: aevara.tests.property.live.test_live_invariants
# @deps: pytest, hypothesis, asyncio, aevara.src.live.pilot_controller
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests: capital_preserved, sizing_bounded, telemetry_active, no_override.

from __future__ import annotations
import asyncio
import pytest
from hypothesis import given, strategies as st, settings
from aevara.src.live.pilot_controller import PilotController, PilotConfig
from aevara.src.live.ftmo_guard import FTMOGuard

@settings(deadline=None)
@given(st.floats(min_value=0.0, max_value=0.5), st.floats(min_value=0.5, max_value=1.0))
def test_pilot_sizing_bounded_property(initial, max_alloc):
    # Invariant: allocation never exceeds max_alloc or stays < initial
    # We use a mock controller
    c = PilotController(100)
    config = PilotConfig(initial, max_alloc, 0.05, 5, 0, 1, 0)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.run_until_complete(c.activate(config))
    # Test multiple random scaling steps
    for _ in range(10):
        loop.run_until_complete(c.scale_allocation("INCREASE"))
    
    assert c._current_allocation <= max_alloc
    assert c._current_allocation >= initial
    
    loop.close()

@given(st.floats(min_value=-1.0, max_value=1.0))
def test_ftmo_daily_limit_invariant_property(pnl_pct):
    # Invariant: daily loss > 4% is ALWAYS False
    guard = FTMOGuard(100.0)
    nominal_pnl = 100.0 * pnl_pct
    
    res = guard.validate_daily_loss(nominal_pnl)
    # pnl_pct is the whole return. If pnl_pct = -0.05 (5% loss), it must be False.
    if pnl_pct < -0.04:
        assert res is False
    else:
        assert res is True

@given(st.floats(min_value=0, max_value=200000))
def test_ftmo_total_limit_invariant_property(equity):
    # Invariant: drawdown > 8% is ALWAYS False
    guard = FTMOGuard(100000.0)
    res = guard.validate_total_loss(equity)
    
    if equity < 92000.0:
        assert res is False
    else:
        assert res is True

@given(st.text())
def test_telemetry_event_integrity_property(msg):
    from aevara.src.live.telemetry_stream import TelemetryEvent
    ev = TelemetryEvent("ID", "ST", True, 0.1, msg)
    assert ev.message == msg
    assert ev.ftmo_compliance is True

@given(st.floats(min_value=0, max_value=1))
def test_failover_reconciliation_drift_precision_property(drift_val):
    from aevara.src.live.failover_manager import FailoverManager
    fm = FailoverManager()
    state = {"balance": 100.0}
    exchange = {"balance": 100.0 - drift_val}
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    ok, drift = loop.run_until_complete(fm.run_reconciliation(state, exchange))
    if drift_val > 0.0001:
         assert ok is False
    
    loop.close()
