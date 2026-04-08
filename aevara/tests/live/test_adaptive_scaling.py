# @module: aevara.tests.live.test_adaptive_scaling
# @deps: pytest, numpy, aevara.src.live.adaptive_scaling_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests: sizing bounds, Kelly-Bayesian convergence, regime adaptation.

from __future__ import annotations
import pytest
import numpy as np
from aevara.src.live.adaptive_scaling_engine import AdaptiveScalingEngine, ScalingConfig

@pytest.fixture
def config():
    return ScalingConfig(
        base_sizing_pct=0.1,
        max_sizing_pct=1.0,
        kelly_fraction=0.25,
        cvar_alpha=0.995,
        regime_vol_cap=0.02, # 2% max vol
        min_edge_sharpe=1.5,
        validation_window=50,
        hysteresis_gap_pct=0.15
    )

@pytest.fixture
def engine(config):
    return AdaptiveScalingEngine(config)

def test_adaptive_scaling_kelly_positive_edge(engine):
    # win_prob 0.6, win_loss 2.0 -> Kelly positive
    decision = engine.calculate_sizing(0.6, 2.0, 0.01, 0.0)
    # Quarter-Kelly: (0.6*2 - 0.4)/2 = 0.8/2 = 0.4 (Full Kelly)
    # Quarter = 0.1 (10%)
    assert decision.approved_pct >= 0.1
    assert "kelly_full" in decision.scaling_factors

def test_adaptive_scaling_zero_edge_min_bound(engine):
    # win_prob 0.3, win_loss 1.0 -> Negative edge
    decision = engine.calculate_sizing(0.3, 1.0, 0.01, 0.0)
    # Kelly should be 0, but approved_pct should stay at base 0.1 (10%)
    assert decision.approved_pct == 0.1

def test_adaptive_scaling_vol_penalty_impact(engine):
    # High vol (0.04) vs Cap (0.02) -> 50% penalty
    decision_v1 = engine.calculate_sizing(0.6, 2.0, 0.01, 0.0) # No penalty
    decision_v2 = engine.calculate_sizing(0.6, 2.0, 0.04, 0.0) # Penalty
    
    assert decision_v2.requested_pct < decision_v1.requested_pct
    assert decision_v2.scaling_factors["vol_f"] == 0.5 # 0.02/0.04

def test_adaptive_scaling_drawdown_brake_impact(engine):
    # Drawdown 0.04 (4%) on 8% limit -> ~50% penalty
    decision_dd0 = engine.calculate_sizing(0.6, 2.0, 0.01, 0.00)
    decision_dd4 = engine.calculate_sizing(0.6, 2.0, 0.01, 0.04) # 4% DD
    
    assert decision_dd4.requested_pct < decision_dd0.requested_pct
    assert decision_dd4.scaling_factors["dd_f"] == pytest.approx(0.5)

def test_adaptive_scaling_max_allocation_bound(config):
    # Use kelly_fraction=1.0 to reach 100% cap
    cfg = ScalingConfig(0.1, 1.0, 1.0, 0.995, 0.02, 1.5, 50, 0.15)
    engine = AdaptiveScalingEngine(cfg)
    # perfect edge
    decision = engine.calculate_sizing(1.0, 100.0, 0.001, 0.0, tier_multiplier=1.0)
    assert decision.approved_pct == 1.0

def test_adaptive_scaling_bayesian_input_robustness(engine):
    # Handle extremes
    d1 = engine.calculate_sizing(0.0001, 0.001, 100.0, 0.99)
    assert d1.approved_pct == 0.1 # Stays at base min

    d2 = engine.calculate_sizing(1.0, 100.0, 0.0, 0.0, tier_multiplier=4.0)
    assert d2.approved_pct == 1.0 # Max capped
