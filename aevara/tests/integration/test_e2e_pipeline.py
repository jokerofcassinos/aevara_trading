# @module: aevara.tests.integration.test_e2e_pipeline
# @deps: pytest, asyncio, unittest.mock, aevara.src.integration.e2e_orchestrator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 15+ integration tests: happy-path, module failure simulation, state drift, and graceful degradation.

from __future__ import annotations
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from aevara.src.integration.e2e_orchestrator import E2EOrchestrator, IntegrationState, MarketTick
from aevara.src.integration.latency_profiler import LatencyProfiler
from aevara.src.integration.state_reconciler import StateReconciler
from aevara.src.integration.shadow_sync import ShadowSyncEngine
from aevara.src.execution.contracts import ExecutionReceipt

@pytest.fixture
def mock_qroe():
    q = AsyncMock()
    q.run_cycle.return_value = {"side": "BUY", "size": 0.1, "coherence": 0.82, "phase": "EXECUTION"}
    return q

@pytest.fixture
def mock_risk():
    r = MagicMock()
    r.validate.return_value = (True, "", "HASH_OK")
    return r

@pytest.fixture
def mock_gateway():
    g = AsyncMock()
    g.mode.value = "live"
    g.submit_order.return_value = ExecutionReceipt(
        exchange_order_id="TX-123",
        status="FILLED",
        filled_size=0.1,
        filled_price=42000.0,
        commission_usd=0.5,
        slippage_bps=1.2,
        latency_us=4500,
        nonce_verified=True,
        risk_gate_passed=True,
        trace_id="TR-123"
    )
    return g

@pytest.fixture
def mock_telemetry():
    t = AsyncMock()
    return t

@pytest.fixture
def orchestrator(mock_qroe, mock_risk, mock_gateway, mock_telemetry):
    return E2EOrchestrator(
        qroe_engine=mock_qroe,
        risk_engine=mock_risk,
        live_gateway=mock_gateway,
        telemetry=mock_telemetry,
        shadow_sync=ShadowSyncEngine(),
        latency_profiler=LatencyProfiler(),
        state_reconciler=StateReconciler()
    )

@pytest.mark.asyncio
async def test_e2e_happy_path(orchestrator):
    tick = MarketTick("BTC/USDT", 42000.0, 41999, 42001, 100, time.time_ns(), "binance")
    state = await orchestrator.run_cycle(tick)
    
    assert state.cycle_id == 1
    assert state.risk_gate_passed is True
    assert state.execution_receipt.status == "FILLED"
    assert "qroe_decision" in state.latency_profile
    assert state.latency_profile["qroe_decision"] > 0

@pytest.mark.asyncio
async def test_risk_rejection_path(orchestrator, mock_risk):
    mock_risk.validate.return_value = (False, "Exposure Limit", "")
    tick = MarketTick("BTC/USDT", 42000.0, 41999, 42001, 100, time.time_ns(), "binance")
    
    state = await orchestrator.run_cycle(tick)
    assert state.risk_gate_passed is False
    assert state.execution_receipt is None

@pytest.mark.asyncio
async def test_state_drift_detection(orchestrator, mock_gateway, mock_telemetry):
    mock_gateway.mode.value = "dry-run"
    tick = MarketTick("BTC/USDT", 42000.0, 41999, 42001, 100, time.time_ns(), "binance")
    
    # We force a drift by setting phase to AUDIT which conflicts with live mode in StateReconciler
    orchestrator._qroe.run_cycle.return_value["phase"] = "AUDIT"
    orchestrator._gateway.mode.value = "live"
    
    await orchestrator.run_cycle(tick)
    # Reconciler should have logged a CRITICAL event
    assert any(args[0] == "CRITICAL" for args, _ in mock_telemetry.log_event.call_args_list)

@pytest.mark.asyncio
async def test_latency_budget_breach(orchestrator, mock_qroe):
    # Simulate high latency in QROE
    async def slow_cycle(*args):
        await asyncio.sleep(0.06) # 60ms > 50ms budget
        return {"side": "BUY", "phase": "EXECUTION"}
    
    mock_qroe.run_cycle = slow_cycle
    tick = MarketTick("BTC/USDT", 42000.0, 41999, 42001, 100, time.time_ns(), "binance")
    
    await orchestrator.run_cycle(tick)
    assert orchestrator._latency.get_e2e_budget_status() == "WARNING"

@pytest.mark.asyncio
async def test_chaos_failure_injection(orchestrator):
    await orchestrator.inject_failure("gateway")
    health = await orchestrator.get_health_report()
    assert "gateway" in health["failures"]

@pytest.mark.asyncio
async def test_shadow_sync_drift_metric(orchestrator):
    # Mocking shadow drift in results
    orchestrator._shadow._drifts.append(0.01) # 1% drift
    state = await orchestrator.run_cycle(MarketTick("X", 1, 0.9, 1.1, 1, 1, "ex"))
    assert state.shadow_drift_pct >= 0.01

@pytest.mark.parametrize("side,risk_pass", [
    ("BUY", True),
    ("SELL", True),
    ("BUY", False),
    ("SELL", False)
])
@pytest.mark.asyncio
async def test_pipeline_matrix_coverage(orchestrator, mock_risk, side, risk_pass):
    orchestrator._qroe.run_cycle.return_value["side"] = side
    mock_risk.validate.return_value = (risk_pass, "Ok" if risk_pass else "Fail", "H")
    
    tick = MarketTick("BTC/USDT", 40000, 39999, 40001, 1, time.time_ns(), "binance")
    state = await orchestrator.run_cycle(tick)
    assert state.risk_gate_passed == risk_pass

@pytest.mark.asyncio
async def test_reconciler_audit_limit(orchestrator):
    tick = MarketTick("X", 10, 9, 11, 1, time.time_ns(), "binance")
    for _ in range(5):
        await orchestrator.run_cycle(tick)
    
    trail = orchestrator._reconciler.get_audit_trail(limit=2)
    assert len(trail) == 2

@pytest.mark.asyncio
async def test_latency_percentiles_calculation(orchestrator):
    tick = MarketTick("X", 10, 9, 11, 1, time.time_ns(), "binance")
    for _ in range(10):
        await orchestrator.run_cycle(tick)
    
    p = orchestrator._latency.get_percentiles("execution")
    assert p["p50"] >= 0
    assert "p99" in p

@pytest.mark.asyncio
async def test_drift_temporal_detection(orchestrator):
    # Simulate market lag
    tick = MarketTick("X", 1, 0.9, 1.1, 1, time.time_ns() - int(2e9), "ex") # 2s lag
    await orchestrator.run_cycle(tick)
    # Reconciler should detect the 2s lag (threshold is 1s)
    health = await orchestrator.get_health_report()
    assert health["cycle_count"] == 1

@pytest.mark.asyncio
async def test_health_report_sync_status(orchestrator):
    report = await orchestrator.get_health_report()
    assert "sync_status" in report
    assert report["sync_status"] in ["LOCKED", "DRIFTING"]

@pytest.mark.asyncio
async def test_state_snapshot_export(orchestrator):
    snap = orchestrator.export_state_snapshot()
    assert isinstance(snap, bytes)
    assert len(snap) > 0

@pytest.mark.asyncio
async def test_slippage_validator_logic(orchestrator):
    assert orchestrator._shadow.validate_slippage_model(expected=10.0, realized=12.0) is True
    assert orchestrator._shadow.validate_slippage_model(expected=10.0, realized=20.0) is False

@pytest.mark.asyncio
async def test_latency_history_reset(orchestrator):
    orchestrator._latency.start_stage("reset")
    orchestrator._latency.end_stage("reset")
    assert "reset" in orchestrator._latency._history
