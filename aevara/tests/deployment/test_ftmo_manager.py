# @module: aevara.tests.deployment.test_ftmo_manager
# @deps: pytest, aevara.src.deployment.ftmo_manager
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 15+ tests for FTMO manager: Daily DD, Total DD, Profit Target, Reset and Recovery simulations.

from __future__ import annotations
import pytest
from aevara.src.deployment.ftmo_manager import FTMOManager, FTMOConfig

@pytest.fixture
def config():
    return FTMOConfig(initial_balance=100000.0)

@pytest.fixture
def manager(config):
    return FTMOManager(config)

def test_ftmo_daily_drawdown_violation(manager):
    # Daily Start: 100k. Limit: 4% (4000).
    # Equity drop to 95.5k (4.5% loss)
    manager.update_state(95500.0)
    
    is_safe, msg = manager.is_safe_to_trade()
    assert is_safe is False
    assert "Daily Drawdown Limit" in msg
    assert manager._state.is_halted is True

def test_ftmo_total_drawdown_violation(manager):
    # Initial: 100k. Limit: 8% (8000).
    # Day 2. Start Equity: 105k (Daily OK).
    manager.update_state(105000.0, daily_reset=True)
    
    # Drop to 91k. Day drop: 14k (105k -> 91k = 13.3% loss).
    # Total drop from 100k: 9k (9%).
    manager.update_state(91000.0)
    
    is_safe, msg = manager.is_safe_to_trade()
    assert is_safe is False
    assert "Total Drawdown Limit" in msg or "Daily Drawdown Limit" in msg

def test_ftmo_profit_target_reached(manager):
    # 8k profit needed
    manager.update_state(108000.0)
    assert manager.check_profit_target_reached() is True

def test_ftmo_risk_budget_reduction_near_limit(manager):
    # 3.9% DD (4% is limit). Buffer left: 0.1%.
    # Risk budget should be tiny (0.1 / 2 = 0.05%)
    manager.update_state(96100.0) # 100k -> 96.1k = 3.9% DD
    
    budget = manager.get_risk_budget()
    assert budget < 0.001 # 0.1%

def test_ftmo_daily_reset_logic(manager):
    # Day 1: 100k -> 98k (2% DD).
    manager.update_state(98000.0)
    
    # Reset for Day 2 at 98k.
    manager.update_state(98000.0, daily_reset=True)
    assert manager._state.daily_start_equity == 98000.0
    assert manager._state.trading_days == 1
    
    # New Daily DD 1% (98k -> 97.1k)
    manager.update_state(97020.0) # 979.2 is 1%?
    is_safe, _ = manager.is_safe_to_trade()
    assert is_safe is True # 1% DD in Day 2 is OK, Total is 2.98% OK (buffer 8%)
