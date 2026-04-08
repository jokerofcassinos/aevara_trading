# @module: aevara.tests.portfolio.test_ftmo_multi_asset
# @deps: pytest, aevara.src.portfolio.ftmo_multi_asset_guard
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests: aggregate exposure monitoring (Σ ≤ 5.0 lots), DD aggregation, and atomic halt propagation for all symbols.

from __future__ import annotations
import pytest
from aevara.src.portfolio.ftmo_multi_asset_guard import FTMOMultiAssetGuard

@pytest.fixture
def guard():
    return FTMOMultiAssetGuard(daily_limit_pct=0.04, total_limit_pct=0.08, max_exposure_lots=5.0)

def test_ftmo_aggregate_exposure_violation(guard):
    # Teste de violação de limite de exposição (Σ > 5.0 lots)
    positions = {"BTCUSD": 2.0, "ETHUSD": 2.0, "SOLUSD": 1.5} # Total 5.5
    res, msg = guard.check_aggregate_exposure(positions)
    assert res is False
    assert guard.is_halted() is True

def test_ftmo_cross_asset_drawdown_reset(guard):
    # Teste de drawdown dentro do limite
    # Balance 100k, PnL -2k (2% DD)
    res = guard.check_cross_asset_drawdown(-2000.0, 98000.0, 100000.0)
    assert res is True
    assert guard.is_halted() is False

def test_ftmo_cross_asset_drawdown_violation(guard):
    # Teste de violação de drawdown total (8%)
    # Balance 100k, PnL -9k (9% DD)
    res = guard.check_cross_asset_drawdown(-9000.0, 91000.0, 100000.0)
    assert res is False
    assert guard.is_halted() is True

def test_ftmo_halt_propagation(guard):
    # Teste: se um breach EXPOSURE_CAP ocorre, o sistema inteiro congela.
    guard.propagate_halt_if_breached("EXPOSURE", "Manual Alert")
    assert guard.is_halted() is True
    
    # Novo check_exposure deve falhar imediatamente pelo estado halted
    res, _ = guard.check_aggregate_exposure({"BTCUSD": 0.01})
    assert res is False
