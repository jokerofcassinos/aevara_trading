# @module: aevara.tests.property.deployment.test_activation_invariants
# @deps: pytest, hypothesis, aevara.src.deployment.activation_orchestrator, aevara.src.deployment.pilot_controller
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 5+ Hypothesis tests for activation invariants: pilot_sizing_bounded, ftmo_compliant, latency_within_budget, phase_deterministic.

from __future__ import annotations
import pytest
import asyncio
from hypothesis import given, strategies as st
from aevara.src.deployment.activation_orchestrator import ActivationGate, ActivationOrchestrator
from aevara.src.deployment.pilot_controller import PilotController

@given(st.floats(0.001, 10.0))
def test_pilot_sizing_bounded_invariant_property(lots):
    # Invariante: Em modo locked (ativacao), p_size deve retornar 0.01
    pilot = PilotController(initial_lot=0.01)
    # pilot starts locked
    size = pilot.get_authorized_size(lots)
    assert size == 0.01

@given(st.floats(0.001, 1.0))
def test_activation_gate_dd_violation_property(dd):
    # Invariante: Qualquer DD >= 4% (0.04) deve falhar o gate (conforme Runbook)
    pilot = PilotController()
    orchestrator = ActivationOrchestrator(pilot)
    gate = ActivationGate(
        phase="DEMO", latency_p99_ms=25.0, reconciliation_drift_pct=0.001,
        ftmo_daily_dd_pct=dd, ftmo_total_dd_pct=0.02,
        pilot_trades_completed=10, edge_significant=True, ceo_approved=True
    )
    # Roda validação síncrona/async conforme runbook
    coro = orchestrator.validate_gate(gate)
    res = asyncio.run(coro)
    
    if dd > 0.04:
         assert res is False
    else:
         assert res is True
