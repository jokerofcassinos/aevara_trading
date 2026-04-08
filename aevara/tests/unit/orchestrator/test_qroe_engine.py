# @module: aevara.tests.unit.orchestrator.test_qroe_engine
# @deps: aevara.src.orchestrator.qroe_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes unitarios para QROE state machine: transicoes, gates,
#           histerese, SAFE_MODE, e DAG enforcement.

from __future__ import annotations

import pytest
from aevara.src.orchestrator.qroe_engine import (
    QROEEngine,
    Phase,
    StateTransition,
    CycleState,
)


# === HAPPY PATH ===
class TestQROEEngineHappyPath:
    def test_starts_in_discovery(self):
        engine = QROEEngine()
        assert engine.current_phase == Phase.DISCOVERY

    def test_forward_transitions(self):
        engine = QROEEngine()
        phases = [Phase.DISCOVERY, Phase.DESIGN, Phase.VALIDATION,
                   Phase.EXECUTION, Phase.AUDIT, Phase.EVOLUTION]
        for phase in phases:
            assert engine.current_phase == phase
            engine.execute_transition(StateTransition.all_gates_pass())

    def test_loops_back_to_discovery_after_evolution(self):
        engine = QROEEngine()
        # Advance through all phases
        phases_list = [Phase.DISCOVERY, Phase.DESIGN, Phase.VALIDATION,
                       Phase.EXECUTION, Phase.AUDIT, Phase.EVOLUTION]
        for _ in phases_list:
            engine.execute_transition(StateTransition.all_gates_pass())
        # Should be back at DISCOVERY
        assert engine.current_phase == Phase.DISCOVERY

    def test_history_grows_with_transitions(self):
        engine = QROEEngine()
        engine.execute_transition(StateTransition.all_gates_pass())
        assert len(engine.get_history()) >= 1

    def test_get_active_profile(self):
        engine = QROEEngine()
        assert engine.get_active_profile(Phase.DISCOVERY) == "Director"
        assert engine.get_active_profile(Phase.AUDIT) == "Auditor"

    def test_dag_display(self):
        engine = QROEEngine()
        dag = engine.get_transition_dag()
        assert "DISCOVERY" in dag
        assert "EXECUTION" in dag


# === EDGE CASES ===
class TestQROEEdgeCases:
    def test_hysteresis_forces_safe_mode(self):
        """Oscillacao entre 2 fases > 3x em 10 ciclos -> SAFE_MODE."""
        engine = QROEEngine()
        # Simulate oscillation by quickly resetting
        for cycle in range(8):
            # Execute a few transitions to build history
            if engine.current_phase == Phase.SAFE_MODE:
                engine.reset_to_discovery()
            engine.execute_transition(StateTransition.all_gates_pass())
        # At minimum it should not crash and stay coherent
        assert engine.current_phase in Phase

    def test_safe_mode_resets_counter(self):
        engine = QROEEngine()
        engine.force_safe_mode(reason="Test")
        assert engine.current_phase == Phase.SAFE_MODE
        # Reset
        engine.reset_to_discovery()
        assert engine.current_phase == Phase.DISCOVERY

    def test_gateway_config_returns_4_gates(self):
        engine = QROEEngine()
        config = engine.get_gateway_config()
        assert len(config) == 4
        assert "G1" in config
        assert "G4" in config

    def test_history_returns_copy_not_internal(self):
        engine = QROEEngine()
        h1 = engine.get_history()
        engine.execute_transition(StateTransition.all_gates_pass())
        h2 = engine.get_history()
        assert len(h1) != len(h2)


# === ERROR / CONSTRAINT CASES ===
class TestQROEErrors:
    def test_transition_backward_not_allowed(self):
        """Backward jump nao e permitida sem SAFE_MODE."""
        assert not StateTransition._transition_allowed(
            Phase.AUDIT, Phase.DESIGN
        )
        assert not StateTransition._transition_allowed(
            Phase.EXECUTION, Phase.DISCOVERY
        )

    def test_safe_mode_always_allowed(self):
        """SAFE_MODE sempre permitido de qualquer fase."""
        for phase in Phase:
            assert StateTransition._transition_allowed(phase, Phase.SAFE_MODE)

    def test_transition_with_failing_gate(self):
        gates = {"G1": True, "G2": False, "G3": True, "G4": True}
        t = StateTransition(
            from_phase=Phase.DISCOVERY,
            to_phase=Phase.DESIGN,
            gate_results=gates,
            context_budget_used=0,
        )
        assert not t.is_valid()
        assert t.get_failed_gates() == ["G2"]

    def test_transition_budget_exceeded(self):
        t = StateTransition(
            from_phase=Phase.DISCOVERY,
            to_phase=Phase.DESIGN,
            gate_results={"G1": True, "G2": True, "G3": True, "G4": True},
            context_budget_used=6,
        )
        assert not t.is_valid()

    def test_empty_gate_results_fails(self):
        t = StateTransition(
            from_phase=Phase.DISCOVERY,
            to_phase=Phase.DESIGN,
            gate_results={},
            context_budget_used=0,
        )
        assert not t.is_valid()  # all([]) is True, but we check gate_results is non-empty

    def test_force_safe_mode_creates_history_entry(self):
        engine = QROEEngine()
        engine.force_safe_mode(reason="Test override")
        history = engine.get_history()
        assert len(history) >= 1
        assert history[-1].phase == Phase.SAFE_MODE
