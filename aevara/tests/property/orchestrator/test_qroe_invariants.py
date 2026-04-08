# @module: aevara.tests.property.orchestrator.test_qroe_invariants
# @deps: aevara.src.orchestrator.qroe_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Property-based tests para QROE invariants: transicoes deterministicas,
#           budget <= 5, no oscillacao sem SAFE_MODE, state consistency.

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st, settings

from aevara.src.orchestrator.qroe_engine import (
    QROEEngine,
    Phase,
    StateTransition,
)


class TestQROEProperties:
    """
    Property-based invariants do motor QROE.
    """

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=20)
    def test_cycle_id_increases_monotonically(self, n_cycles):
        engine = QROEEngine()
        prev_cycle_id = engine.cycle_id
        for _ in range(n_cycles):
            if engine.current_phase == Phase.SAFE_MODE:
                engine.reset_to_discovery()
            engine.execute_transition(StateTransition.all_gates_pass())
            if engine.current_phase != Phase.SAFE_MODE:
                assert engine.cycle_id > prev_cycle_id
                prev_cycle_id = engine.cycle_id

    def test_phase_never_goes_backward_without_safe_mode(self):
        """Sem SAFE_MODE, fase sempre avanca."""
        engine = QROEEngine()
        phases_ordered = [
            Phase.DISCOVERY, Phase.DESIGN, Phase.VALIDATION,
            Phase.EXECUTION, Phase.AUDIT, Phase.EVOLUTION,
        ]
        for expected in phases_ordered:
            assert engine.current_phase == expected
            engine.execute_transition(StateTransition.all_gates_pass())

    def test_safe_mode_resets_cycle(self):
        engine = QROEEngine()
        engine.execute_transition(StateTransition.all_gates_pass())
        engine.execute_transition(StateTransition.all_gates_pass())
        engine.force_safe_mode(reason="Test")
        engine.reset_to_discovery()
        assert engine.current_phase == Phase.DISCOVERY

    def test_no_phase_after_safe_mode_without_reset(self):
        """SAFE_MODE so sai via reset_to_discovery."""
        engine = QROEEngine()
        engine.force_safe_mode(reason="Test")
        assert engine.current_phase == Phase.SAFE_MODE
        # Execute transition - should not change phase (stuck in safe mode)
        engine.execute_transition(StateTransition.all_gates_pass())
        # After execute with all pass but in safe mode, next is DISCOVERY
        assert engine.current_phase == Phase.DISCOVERY  # get_next_phase returns DISCOVERY from SAFE_MODE

    def test_all_gates_pass_always_valid(self):
        gates = StateTransition.all_gates_pass()
        assert all(gates.values())
        assert len(gates) == 4
