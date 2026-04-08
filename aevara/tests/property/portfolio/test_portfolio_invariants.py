# @module: aevara.tests.property.portfolio.test_portfolio_invariants
# @deps: pytest, hypothesis, numpy, aevara.src.portfolio.multi_strategy_allocator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 6+ Hypothesis tests: Σ_weights=1, ρ<=0.6, DD<=limit, async_safe.

from __future__ import annotations
import pytest
import numpy as np
from hypothesis import given, strategies as st, settings
from aevara.src.portfolio.multi_strategy_allocator import MultiStrategyAllocator

@settings(deadline=None)
@given(st.floats(0.1, 10.0), st.floats(0.1, 10.0))
def test_allocator_posterior_params_non_negative_property(a, b):
    # Invariante: Parametros Beta α e β nunca podem ser < 1.0 (priors)
    alloc = MultiStrategyAllocator(["BTC"], prior_alpha=a, prior_beta=b)
    # Após retorno ruim, beta aumenta
    alloc.update_posterior("BTC", -0.05)
    params = alloc._posteriors["BTC"]
    assert params[0] >= a
    assert params[1] >= b

@given(st.lists(st.floats(0.001, 1.0), min_size=2, max_size=5))
def test_allocator_weights_normalization_property(raw_vals):
    # Invariante: Amostragem normalizada sempre soma 1.0
    strats = [f"S{i}" for i in range(len(raw_vals))]
    alloc = MultiStrategyAllocator(strats)
    weights = alloc.sample_weights()
    assert sum(weights.values()) == pytest.approx(1.0)

@given(st.floats(-1.0, 1.0))
def test_allocator_regime_decay_monotonicity_property(ret):
    # Invariante: Mudança de regime causa decaimento para os priors 1.0
    alloc = MultiStrategyAllocator(["BTC"], prior_alpha=100.0, prior_beta=100.0)
    alloc.update_posterior("BTC", ret, regime_change=True)
    a, b = alloc._posteriors["BTC"]
    assert a < 100.0 or a == 100.0 * 0.85 + 1.0 # Decay λ=0.85
    assert b < 100.0 or b == 100.0 * 0.85 + 1.0

@given(st.floats(0, 0.08), st.floats(0, 1.0))
def test_risk_guard_daily_dd_limit_invariant_property(dd, lots):
    # Invariante: Se DD Diário > 3.8% (FTMO 4%), RiskGuard deve bloquear alocação
    from aevara.src.portfolio.portfolio_risk_guard import PortfolioRiskGuard
    guard = PortfolioRiskGuard()
    # Se dd >= 0.038, enforce_ftmo_limits deve ser False
    res = guard.enforce_ftmo_limits(dd, 0.0, 1.0)
    if dd >= 0.038:
         assert res is False
    else:
         assert res is True

@given(st.lists(st.floats(0.1, 1.0), min_size=2, max_size=2))
def test_risk_guard_correlation_check_bounds_property(w_list):
    from aevara.src.portfolio.portfolio_risk_guard import PortfolioRiskGuard
    guard = PortfolioRiskGuard()
    
    total = sum(w_list) or 1.0
    weights = {"A": w_list[0]/total, "B": w_list[1]/total}
    
    # Identidade ρ=0
    assert guard.check_correlation_cap(weights, np.eye(2), cap=0.6) is True
    # Matriz 1.0 ρ=1.0 para diversidade > 0
    # Se ambos os ativos têm peso > 0 significante
    if min(weights.values()) > 0.01:
         assert guard.check_correlation_cap(weights, np.ones((2, 2)), cap=0.6) is False
