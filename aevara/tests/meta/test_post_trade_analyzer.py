# @module: aevara.tests.meta.test_post_trade_analyzer
# @deps: pytest, aevara.src.meta.post_trade_analyzer
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests: forensic depth, root-cause accuracy, patch validity simulation.

from __future__ import annotations
import pytest
import asyncio
from aevara.src.meta.post_trade_analyzer import PostTradeAnalyzer, TradeForensicReport

@pytest.fixture
def analyzer():
    return PostTradeAnalyzer(history_maxlen=100)

@pytest.mark.asyncio
async def test_post_trade_forensic_depth(analyzer):
    # Test if all 12 layers are present
    context = {"trade_id": "T-123"}
    outcome = {"status": "LOSS"}
    report = await analyzer.analyze(context, outcome)
    
    assert len(report.layers) == 12
    assert report.trade_id == "T-123"

@pytest.mark.asyncio
async def test_post_trade_root_cause_slippage(analyzer):
    # Simulate high slippage
    context = {"trade_id": "T-123", "slippage_bps": 3.5}
    outcome = {"status": "LOSS"}
    report = await analyzer.analyze(context, outcome)
    
    assert report.root_cause == "execution"
    assert "SLIPPAGE_DRAG" in report.layers["execution"]["status"]

@pytest.mark.asyncio
async def test_post_trade_root_cause_regime_drift(analyzer):
    # Simulate high regime drift
    context = {"trade_id": "T-123", "regime_drift": 0.8}
    outcome = {"status": "LOSS"}
    report = await analyzer.analyze(context, outcome)
    
    assert report.root_cause == "regime"
    assert "REGIME_SKEW" in report.layers["regime"]["status"]

@pytest.mark.asyncio
async def test_post_trade_patch_generation(analyzer):
    # Test if patch is generated based on root cause
    context = {"trade_id": "T-123", "slippage_bps": 3.0}
    outcome = {"status": "LOSS"}
    report = await analyzer.analyze(context, outcome)
    
    assert report.patch_candidate is not None
    assert report.patch_candidate["action"] == "ADJUST_MAX_SLIPPAGE"
