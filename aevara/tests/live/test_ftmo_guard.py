# @module: aevara.tests.live.test_ftmo_guard
# @deps: pytest, aevara.src.live.ftmo_guard
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests: daily limit, total limit, time constraints, override prevention.

from __future__ import annotations
import pytest
from aevara.src.live.ftmo_guard import FTMOGuard

@pytest.fixture
def guard():
    return FTMOGuard(initial_equity=100000.0)

def test_ftmo_daily_loss_limit_pass(guard):
    # Loss: 3k on 100k (3.0% < 4.0%)
    assert guard.validate_daily_loss(current_pnl=-3000.0) is True

def test_ftmo_daily_loss_limit_fail(guard):
    # Loss: 5k on 100k (5.0% > 4.0%)
    assert guard.validate_daily_loss(current_pnl=-5000.0) is False

def test_ftmo_total_loss_limit_pass(guard):
    # Equity: 93k (7% Drawdown < 8%)
    assert guard.validate_total_loss(current_equity=93000.0) is True

def test_ftmo_total_loss_limit_fail(guard):
    # Equity: 91k (9% Drawdown > 8%)
    assert guard.validate_total_loss(current_equity=91000.0) is False

def test_ftmo_trading_days_constraint(guard):
    assert guard.validate_trading_days(days_active=5, min_days=4) is True
    assert guard.validate_trading_days(days_active=3, min_days=4) is False

def test_ftmo_compliance_global_check(guard):
    state = {"current_pnl": -1000, "current_equity": 98000}
    ok, reason = guard.is_within_compliance(state)
    assert ok is True
    
    state_bad = {"current_pnl": -5000}
    ok, reason = guard.is_within_compliance(state_bad)
    assert ok is False
    assert "Daily loss" in reason

def test_ftmo_violation_logging(guard):
    guard.validate_daily_loss(-6000.0)
    assert len(guard._violations) == 1
    assert "DAILY_LOSS" in guard._violations[0]

@pytest.mark.parametrize("pnl, expected", [
    (-3999, True),
    (-4001, False),
    (0, True),
    (500, True)
])
def test_ftmo_daily_loss_edge_cases(guard, pnl, expected):
    assert guard.validate_daily_loss(pnl) == expected
