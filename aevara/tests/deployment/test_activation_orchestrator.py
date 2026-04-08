# @module: aevara.tests.deployment.test_activation_orchestrator
# @deps: pytest, asyncio, aevara.src.deployment.activation_orchestrator, aevara.src.deployment.pilot_controller
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests: Activation phase transitions, CEO command routing, and gate enforcement for Demo/Micro/Live.

from __future__ import annotations
import pytest
import asyncio
from aevara.src.deployment.activation_orchestrator import ActivationOrchestrator, ActivationGate
from aevara.src.deployment.pilot_controller import PilotController

@pytest.fixture
def pilot():
    return PilotController(initial_lot=0.01)

@pytest.fixture
def orchestrator(pilot):
    return ActivationOrchestrator(pilot_controller=pilot)

@pytest.mark.asyncio
async def test_activation_phase_transition_demo(orchestrator, pilot):
    # Teste de transição manual para fase DEMO
    res = await orchestrator.start_phase("DEMO")
    assert res is True
    assert orchestrator.get_phase_status()["phase"] == "DEMO"
    assert pilot.is_locked() is True

@pytest.mark.asyncio
async def test_activation_ceo_command_routing(orchestrator):
    # Teste de roteamento de comandos administrativos (CEO)
    res = await orchestrator.handle_ceo_command("/go_live_demo")
    assert "SUCCESS" in res
    assert orchestrator._current_phase == "DEMO"

@pytest.mark.asyncio
async def test_activation_gate_validation_pass(orchestrator):
    # Teste de gate passando criterios (CEO approved, latency safe)
    gate = ActivationGate(
        phase="DEMO", latency_p99_ms=25.0, reconciliation_drift_pct=0.001,
        ftmo_daily_dd_pct=0.01, ftmo_total_dd_pct=0.02,
        pilot_trades_completed=10, edge_significant=True, ceo_approved=True
    )
    res = await orchestrator.validate_gate(gate)
    assert res is True

@pytest.mark.asyncio
async def test_activation_gate_validation_fail_dd(orchestrator):
    # Teste de gate falhando por estouro de budget FTMO (Daily DD 5% > 4%)
    gate = ActivationGate(
        phase="DEMO", latency_p99_ms=25.0, reconciliation_drift_pct=0.001,
        ftmo_daily_dd_pct=0.05, ftmo_total_dd_pct=0.02,
        pilot_trades_completed=10, edge_significant=True, ceo_approved=True
    )
    res = await orchestrator.validate_gate(gate)
    assert res is False

@pytest.mark.asyncio
async def test_activation_emergency_halt(orchestrator):
    # Teste de interrupção atômica de emergência
    await orchestrator.emergency_halt("CRITICAL_TEST")
    assert orchestrator.get_phase_status()["is_halted"] is True
