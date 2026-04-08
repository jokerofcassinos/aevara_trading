# @module: aevara.tests.portfolio.test_risk_guard
# @deps: pytest, numpy, aevara.src.portfolio.portfolio_risk_guard
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 8+ tests: CVaR bounds, FTMO limits, correlation cap enforcement.

from __future__ import annotations
import pytest
import numpy as np
from aevara.src.portfolio.portfolio_risk_guard import PortfolioRiskGuard

@pytest.fixture
def guard():
    # max_cvar=1.8%, max_corr=0.6, max_lots=5.0
    return PortfolioRiskGuard(0.018, 0.6, 5.0)

def test_risk_guard_cvar_calculation(guard):
    # Retornos com cauda longa: 0.1% chance de perda -2%
    rets = np.random.normal(0.001, 0.005, 1000)
    rets[0] = -0.05 # Outlier/Fat-tail
    
    cvar = guard.compute_portfolio_cvar(rets, alpha=0.99)
    # CVaR (99%) deve ser aprox a media dos top 1% piores retornos (-0.05)
    assert cvar >= 0.01

def test_risk_guard_validate_allocation_sum_weights(guard):
    w = {"BTC": 0.4, "ETH": 0.4} # Sum 0.8 != 1.0
    res, msg = guard.validate_allocation(w, ["BTC", "ETH"])
    assert res is False
    assert "Sum weights" in msg

def test_risk_guard_correlation_cap_pass(guard):
    w = {"BTC": 0.5, "ETH": 0.5}
    # Matrix identidade ρ=0 (independência)
    matrix = np.eye(2)
    assert guard.check_correlation_cap(w, matrix, cap=0.6) is True

def test_risk_guard_correlation_cap_fail(guard):
    w = {"BTC": 0.5, "ETH": 0.5}
    # Alta correlação ρ=1.0 em todos pares
    matrix = np.ones((2, 2)) # Every correlation is 1.0!
    # Weighted corr = 0.5*1.0*0.5*4 (for all pairs) = 1.0
    assert guard.check_correlation_cap(w, matrix, cap=0.6) is False

def test_risk_guard_ftmo_daily_limit_enforce(guard):
    # DD daily 3.9% excede buffer 3.8%
    assert guard.enforce_ftmo_limits(0.039, 0.0, 1.0) is False
    # DD daily 1.0% dentro dos limites
    assert guard.enforce_ftmo_limits(0.010, 0.0, 1.0) is True

def test_risk_guard_max_lots_limit_enforce(guard):
    # 6.0 lots excede 5.0 max_lots
    assert guard.enforce_ftmo_limits(0, 0, 6.0) is False
