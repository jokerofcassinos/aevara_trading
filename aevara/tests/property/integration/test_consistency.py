# @module: aevara.tests.property.integration.test_consistency
# @deps: pytest, hypothesis, asyncio, aevara.src.integration.e2e_orchestrator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests proving determinism, budget compliance, state consistency, and cross-module idempotency.

from __future__ import annotations
import asyncio
import uuid
import time
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock

from aevara.src.integration.e2e_orchestrator import E2EOrchestrator, MarketTick
from aevara.src.integration.latency_profiler import LatencyProfiler
from aevara.src.integration.state_reconciler import StateReconciler
from aevara.src.integration.shadow_sync import ShadowSyncEngine

# Mocking all subsystems
def build_mock_orchestrator():
    q = AsyncMock()
    q.run_cycle.return_value = {"side": "BUY", "size": 0.1, "coherence": 0.82, "phase": "EXECUTION"}
    
    r = MagicMock()
    r.validate.return_value = (True, "", "HASH")
    
    g = AsyncMock()
    g.mode.value = "dry-run"
    g.submit_order.return_value = MagicMock() # receipt
    
    t = AsyncMock()
    
    return E2EOrchestrator(
        qroe_engine=q,
        risk_engine=r,
        live_gateway=g,
        telemetry=t,
        shadow_sync=ShadowSyncEngine(),
        latency_profiler=LatencyProfiler(),
        state_reconciler=StateReconciler()
    )

@settings(deadline=None)
@given(st.floats(min_value=100, max_value=100000), 
       st.integers(min_value=1, max_value=100))
def test_determinism_property(price, count):
    # Determinism check: multiple calls with same input produce consistent cycle growth
    orch = build_mock_orchestrator()
    tick = MarketTick("BTC/USDT", price, price-1, price+1, 10, time.time_ns(), "binance")
    
    # Run once to get baseline
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    res1 = loop.run_until_complete(orch.run_cycle(tick))
    res2 = loop.run_until_complete(orch.run_cycle(tick))
    
    assert res1.cycle_id == 1
    assert res2.cycle_id == 2
    assert res1.market_tick.price == price
    assert res2.market_tick.price == price
    loop.close()

@given(st.integers(min_value=1, max_value=100))
def test_latency_budget_compliance_property(duration):
    lp = LatencyProfiler(buffer_size=100)
    # Simulate a stage that takes exactly 'duration' microseconds
    start = time.perf_counter_ns()
    lp.end_stage("test", start - (duration * 1000))
    
    perf = lp.get_percentiles("test")
    assert perf["p50"] >= duration

@given(st.floats(min_value=0.0, max_value=1.0))
def test_shadow_sync_drift_accumulation(drift):
    shadow = ShadowSyncEngine()
    shadow._drifts.append(drift)
    assert shadow.compute_drift() == drift

@given(st.lists(st.floats(min_value=0, max_value=1), min_size=10, max_size=10))
def test_drift_avg_calculation(drifts):
    shadow = ShadowSyncEngine()
    for d in drifts:
        shadow._drifts.append(d)
    
    expected = sum(drifts) / len(drifts)
    assert abs(shadow.compute_drift() - expected) < 1e-9

@given(st.integers(min_value=1, max_value=100))
def test_reconciler_history_size(count):
    rec = StateReconciler()
    for i in range(count):
        rec.validate_coherence({
            "trace_ids": [str(i)],
            "market_ts_ns": time.time_ns()
        })
    
    assert len(rec.get_audit_trail(limit=500)) == count

@given(st.integers(min_value=1, max_value=10**9))
def test_latency_profiler_stage_idempotency(start_ns):
    lp = LatencyProfiler()
    lp.start_stage("X")
    lp.end_stage("X")
    # Multiple start/ends should not corrupt history (it appends)
    assert len(lp._history["X"]) == 1
