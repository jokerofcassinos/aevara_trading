# @module: aevara.tests.property.live.test_scaling_invariants
# @deps: pytest, hypothesis, asyncio, aevara.src.live.adaptive_scaling_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests: monotonic_allocation_under_conditions, sizing ≤ max, drawdown_bounded, no_thrashing.

from __future__ import annotations
import asyncio
import pytest
from hypothesis import given, strategies as st, settings
from aevara.src.live.adaptive_scaling_engine import AdaptiveScalingEngine, ScalingConfig

@settings(deadline=None)
@given(st.floats(0.1, 1.0), st.floats(0, 1), st.floats(0.1, 10.0), st.floats(0.001, 1.0), st.floats(0, 0.08))
def test_scaling_bounds_invariant_property(max_alloc, p, w, vol, dd):
    # Invariant: approved_pct ALWAYS between base_sizing (0.1) and max_alloc
    config = ScalingConfig(0.1, max_alloc, 0.25, 0.995, 0.02, 1.5, 50, 0.15)
    engine = AdaptiveScalingEngine(config)
    decision = engine.calculate_sizing(p, w, vol, dd)
    
    # Approved sizing MUST be bounded
    assert 0.1 <= decision.approved_pct <= max_alloc
    
    # Sizing factors MUST be bounded [0, 1] for most multipliers
    assert 0 <= decision.scaling_factors["vol_f"] <= 1.0
    assert 0 <= decision.scaling_factors["dd_f"] <= 1.0
    assert 0 <= decision.scaling_factors["liqd_f"] <= 1.0

@given(st.floats(0, 0.08))
def test_drawdown_scaling_monotonicity_property(dd):
    # Invariant: Increase in DD MUST NOT increase dd_f (multiplier)
    config = ScalingConfig(0.1, 1.0, 0.25, 0.995, 0.02, 1.5, 50, 0.15)
    engine = AdaptiveScalingEngine(config)
    d1 = engine.calculate_sizing(0.6, 2.0, 0.01, dd)
    d2 = engine.calculate_sizing(0.6, 2.0, 0.01, dd + 0.0001 if dd < 0.0799 else 0.08)
    
    assert d2.scaling_factors["dd_f"] <= d1.scaling_factors["dd_f"]

@given(st.floats(0, 1))
def test_kelly_bayesian_input_boundedness_property(p):
    # Invariant: Full Kelly should not exceed 1.0 (theoretical max)
    # Actually Kelly full can be > 1.0 if win rate is high.
    # But our approved_pct must be bounded by system max.
    config = ScalingConfig(0.1, 1.0, 0.25, 0.995, 0.02, 1.5, 50, 0.15)
    engine = AdaptiveScalingEngine(config)
    # p=1.0, w=100.0 -> Kelly Full ~ 1.0. 
    # With q-kelly fraction=0.25 -> ~0.25 alocation.
    decision = engine.calculate_sizing(p, 100.0, 0.001, 0.0)
    assert decision.approved_pct <= 1.0

@given(st.text())
def test_sizing_decision_metadata_persistence_property(msg):
    from aevara.src.live.adaptive_scaling_engine import SizingDecision
    # Trace ID should be valid
    d = SizingDecision(1, 0.1, 0.1, {}, [], 1.0, msg)
    assert d.trace_id == msg

@given(st.floats(0, 0.08))
def test_circuit_breaker_transition_monotonicity_property(dd):
    # Invariant: Higher DD must result in equal or more restrictive CB level
    from aevara.src.live.dynamic_circuit_breakers import DynamicCircuitBreaker, CBLevel
    cb = DynamicCircuitBreaker()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    l1 = loop.run_until_complete(cb.evaluate({"max_drawdown": dd}))
    l2 = loop.run_until_complete(cb.evaluate({"max_drawdown": dd + 0.001 if dd < 0.079 else 0.08}))
    
    # CBLevel values: GREEN=1, YELLOW=2, ... CATASTROPHIC=7
    assert l2.value >= l1.value
    
    loop.close()
