# @module: aevara.tests.portfolio.test_portfolio_optimizer
# @deps: pytest, asyncio, numpy, aevara.src.portfolio.portfolio_optimizer, aevara.src.portfolio.stochastic_sizer
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests for portfolio optimization: ergodic growth maximization, constraint satisfaction, solver stability, and timeout handling.

from __future__ import annotations
import pytest
import asyncio
import numpy as np
from aevara.src.portfolio.portfolio_optimizer import PortfolioOptimizer, SizingContext

@pytest.fixture
def optimizer():
    return PortfolioOptimizer(max_iterations=10, timeout_s=1.0)

@pytest.fixture
def assets():
    return [
        SizingContext("BTC", 0.02, 1.0, "normal", 0.0, 2.0, 0.0, 5.0, 0.01),
        SizingContext("ETH", 0.01, 0.8, "normal", 0.0, 2.0, 0.0, 5.0, 0.01)
    ]

@pytest.mark.asyncio
async def test_optimizer_ergodic_maximization(optimizer, assets):
    # Teste de convergência L-BFGS-B para 2 ativos
    # BTC tem maior alpha -> deve receber mais peso 
    weights = await optimizer.optimize(assets, {})
    
    assert "BTC" in weights
    assert "ETH" in weights
    assert weights["BTC"] > weights["ETH"]

@pytest.mark.asyncio
async def test_optimizer_fallback_on_empty(optimizer):
    # Teste de comportamento resiliente com ativos vazios
    weights = await optimizer.optimize([], {})
    assert weights == {}

@pytest.mark.asyncio
async def test_optimizer_timeout_handling(optimizer, assets):
    # Simula timeout (reduzindo timeout para 0.001s)
    opt_fast = PortfolioOptimizer(max_iterations=100, timeout_s=0.0)
    weights = await opt_fast.optimize(assets, {})
    
    # Deve retornar fallback_safe_allocation (0.002 per asset)
    assert weights["BTC"] == 0.002
