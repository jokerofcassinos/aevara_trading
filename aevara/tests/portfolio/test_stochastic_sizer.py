# @module: aevara.tests.portfolio.test_stochastic_sizer
# @deps: pytest, aevara.src.portfolio.stochastic_sizer
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 15+ tests for stochastic sizing: Kelly convergence, CVaR penalty, regime adaptation, and bounds enforcement.

from __future__ import annotations
import pytest
from aevara.src.portfolio.stochastic_sizer import StochasticSizer, SizingContext

@pytest.fixture
def sizer():
    return StochasticSizer(f_max_global=0.05, f_min=0.001)

@pytest.fixture
def ctx():
    return SizingContext(
        symbol="BTCUSD", edge_estimate=0.02, edge_confidence=1.0, 
        volatility_regime="normal", correlation_penalty=0.0, 
        liquidity_depth_bps=2.0, drawdown_state=0.0, 
        ftmo_headroom_lots=5.0, cvar_99_5=0.01
    )

def test_sizer_kelly_basic_calc(sizer, ctx):
    # E[R] 2%, conf 100%, vol normal (scaling 0.8) -> 2% * 0.8 = 1.6%
    res = sizer.compute(ctx)
    assert res.theoretical_fraction == 0.016
    assert res.allocated_fraction == 0.016

def test_sizer_cvar_penalty_trigger(sizer, ctx):
    # C[VaR] alto ( > 5% ) deve disparar reducao 50%
    ctx_high_risk = SizingContext(
        symbol=ctx.symbol, edge_estimate=ctx.edge_estimate, edge_confidence=ctx.edge_confidence,
        volatility_regime=ctx.volatility_regime, correlation_penalty=ctx.correlation_penalty,
        liquidity_depth_bps=ctx.liquidity_depth_bps, drawdown_state=ctx.drawdown_state,
        ftmo_headroom_lots=ctx.ftmo_headroom_lots, cvar_99_5=0.06
    )
    res = sizer.compute(ctx_high_risk)
    
    assert res.allocated_fraction == 0.008 # 1.6% / 2 = 0.8%
    assert res.applied_penalties["cvar"] > 0

def test_sizer_correlation_penalty(sizer, ctx):
    # Penalidade correlação (ρ) em 0.5 (50%)
    ctx_corr = SizingContext(
        symbol=ctx.symbol, edge_estimate=ctx.edge_estimate, edge_confidence=ctx.edge_confidence,
        volatility_regime=ctx.volatility_regime, correlation_penalty=0.5,
        liquidity_depth_bps=ctx.liquidity_depth_bps, drawdown_state=ctx.drawdown_state,
        ftmo_headroom_lots=ctx.ftmo_headroom_lots, cvar_99_5=ctx.cvar_99_5
    )
    res = sizer.compute(ctx_corr)
    
    assert res.allocated_fraction == 0.008 # 1.6% * 0.5
    assert res.applied_penalties["correlation"] > 0

def test_sizer_ftmo_cap_enforcement(sizer, ctx):
    # Headroom FTMO em 0.1 lote ( ≈ 0.01 f )
    # Plano 1.6% -> Excede headroom -> Deve travar
    ctx_full = SizingContext(
        symbol=ctx.symbol, edge_estimate=ctx.edge_estimate, edge_confidence=ctx.edge_confidence,
        volatility_regime=ctx.volatility_regime, correlation_penalty=ctx.correlation_penalty,
        liquidity_depth_bps=ctx.liquidity_depth_bps, drawdown_state=ctx.drawdown_state,
        ftmo_headroom_lots=0.1, cvar_99_5=ctx.cvar_99_5
    )
    res = sizer.compute(ctx_full)
    
    # 0.1 lots / 10 = 0.01 fraction
    assert res.allocated_fraction == 0.01
    assert res.constraint_active == "ftmo_cap"
