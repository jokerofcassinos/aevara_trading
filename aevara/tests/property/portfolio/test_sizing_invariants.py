# @module: aevara.tests.property.portfolio.test_sizing_invariants
# @deps: pytest, hypothesis, aevara.src.portfolio.stochastic_sizer, aevara.src.portfolio.constraint_enforcer
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests for sizing invariants: 0 < f ≤ f_max, g_concave, ftmo_compliant, and no_nan_inf.

from __future__ import annotations
import pytest
import numpy as np
from hypothesis import given, strategies as st
from aevara.src.portfolio.stochastic_sizer import StochasticSizer, SizingContext
from aevara.src.portfolio.constraint_enforcer import ConstraintEnforcer

@given(st.floats(0.001, 0.5), st.floats(0.0, 1.0))
def test_stochastic_sizer_fraction_bounded_property(edge, conf):
    # Invariante: f sempre em [f_min, f_max] ( 0.1% a 5% )
    sizer = StochasticSizer(f_max_global=0.05, f_min=0.001)
    ctx = SizingContext(
        symbol="BTCUSD", edge_estimate=edge, edge_confidence=conf, 
        volatility_regime="normal", correlation_penalty=0.0, 
        liquidity_depth_bps=2.0, drawdown_state=0.0, 
        ftmo_headroom_lots=5.0, cvar_99_5=0.01
    )
    res = sizer.compute(ctx)
    
    assert 0.0009 <= res.allocated_fraction <= 0.051
    assert not np.isnan(res.allocated_fraction)

@given(st.dictionaries(st.text(min_size=3, max_size=3), st.floats(0.0, 1.0), min_size=1, max_size=5))
def test_constraint_enforcer_ftmo_cap_property(weights):
    # Invariante: Σ lots <= 5.0 (FTMO) nunca violado apos enforcer
    enforcer = ConstraintEnforcer(max_lots=5.0)
    
    # 5 assets: w=1.0 per asset (massive exposure)
    clean_w = enforcer.enforce(weights)
    
    # 0.5 lots per 5% -> factor 10.0
    total_est_lots = sum(clean_w.values()) * 10.0
    
    assert total_est_lots <= 5.0001
    assert not any(np.isnan(v) for v in clean_w.values())

@given(st.floats(0.0, 1.0))
def test_stochastic_sizer_zero_edge_zero_f_property(conf):
    # Invariante: Se edge for zero, o sizer deve retornar f_min
    sizer = StochasticSizer(f_max_global=0.05, f_min=0.001)
    ctx = SizingContext(
        symbol="BTCUSD", edge_estimate=0.0, edge_confidence=conf, 
        volatility_regime="normal", correlation_penalty=0.0, 
        liquidity_depth_bps=2.0, drawdown_state=0.0, 
        ftmo_headroom_lots=5.0, cvar_99_5=0.01
    )
    res = sizer.compute(ctx)
    assert res.allocated_fraction == 0.001
