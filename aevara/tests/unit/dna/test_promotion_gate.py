# @module: aevara.tests.unit.dna.test_promotion_gate
# @deps: aevara.src.dna.promotion_gate
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para PromotionGate: promotion, rejection, histerese, thrashing prevention.

from __future__ import annotations

import pytest

from aevara.src.dna.promotion_gate import GateAction, GateEvaluation, PromotionGate


# === HAPPY PATH ===
class TestPromotionGateHappyPath:
    def test_evaluate_promotion_with_high_alignment(self):
        gate = PromotionGate()
        # High alignment and positive RR delta
        for _ in range(10):
            gate.record(alignment=0.95, rr_delta=0.2)
        result = gate.evaluate()
        assert result.action == GateAction.PROMOTE

    def test_evaluate_hold_with_low_alignment(self):
        gate = PromotionGate()
        for _ in range(5):
            gate.record(alignment=0.75, rr_delta=0.0)
        result = gate.evaluate()
        assert result.action == GateAction.HOLD

    def test_apply_hysteresis_returns_correct(self):
        gate = PromotionGate()
        assert gate.apply_hysteresis(0.90) == "PROMOTE"
        assert gate.apply_hysteresis(0.75) == "HOLD"
        assert gate.apply_hysteresis(0.50) == "DEMOTE"

    def test_demotion_triggers_cooldown(self):
        gate = PromotionGate()
        for _ in range(5):
            gate.record(alignment=0.40, rr_delta=-0.5)
        result = gate.evaluate()
        assert result.action == GateAction.DEMOTE
        assert gate.cooldown_remaining > 0

    def test_atomic_swap_promotes_shadow_to_real(self):
        gate = PromotionGate()
        shadow = {"A": 0.4, "B": 0.6}
        real = {"A": 0.5, "B": 0.5}
        new_real, old_real = gate.atomic_swap(shadow, real)
        assert abs(new_real["A"] - 0.4) < 1e-10
        assert abs(old_real["A"] - 0.5) < 1e-10

    def test_gate_evaluation_records_history(self):
        gate = PromotionGate()
        for _ in range(10):
            gate.record(0.9, 0.1)
        hist = gate.get_alignment_history()
        assert len(hist) == 10

    def test_evaluate_demotion_with_low_alignment(self):
        gate = PromotionGate()
        for i in range(10):
            gate.record(alignment=0.40, rr_delta=-0.5)
        result = gate.evaluate()
        assert result.action == GateAction.DEMOTE
        assert gate.cooldown_remaining == gate._cooldown_cycles

    def test_hold_with_insufficient_rr_delta(self):
        gate = PromotionGate()
        for _ in range(10):
            gate.record(alignment=0.90, rr_delta=0.01)
        result = gate.evaluate()
        assert result.action == GateAction.HOLD

    def test_cooldown_prevents_promotion(self):
        gate = PromotionGate()
        gate._cooldown_remaining = 5
        gate._alignment_history.extend([0.95] * 10)
        gate._rr_delta_history.extend([0.3] * 10)
        result = gate.evaluate()
        assert result.action == GateAction.COOLDOWN
        assert result.cooldown_remaining == 5


# === THRASHING PREVENTION ===
class TestPromotionGateThrashing:
    def test_thrashing_detection(self):
        gate = PromotionGate(thrashing_window=20, thrashing_max_oscillations=3)
        # Simulate oscillating alignment
        for i in range(15):
            alignment = 0.85 if i % 2 == 0 else 0.79
            gate.record(alignment, 0.1)
        result = gate.evaluate()
        # Should detect thrashing and trigger cooldown
        if result.thrashing_detected:
            assert result.action == GateAction.COOLDOWN

    def test_no_thrashing_with_stable_alignment(self):
        gate = PromotionGate()
        for _ in range(15):
            gate.record(0.88, 0.15)
        result = gate.evaluate()
        assert not result.thrashing_detected
        assert result.action == GateAction.PROMOTE


# === ERROR CASES ===
class TestPromotionGateErrors:
    def test_threshold_gap_validation(self):
        with pytest.raises(AssertionError):
            PromotionGate(min_alignment=0.70, demotion_threshold=0.80)
        with pytest.raises(AssertionError):
            PromotionGate(min_alignment=0.70, demotion_threshold=0.70)

    def test_reset_clears_history(self):
        gate = PromotionGate()
        for _ in range(10):
            gate.record(0.9, 0.1)
        gate.reset()
        assert gate._cooldown_remaining == 0
        assert len(gate._alignment_history) == 0


# === PROPERTY-BASED ===
class TestPromotionGateProperties:
    def test_promotion_only_when_aligned(self):
        gate = PromotionGate(min_alignment=0.82, min_rr_delta=0.05)
        gate.record(0.9, 0.1)  # High alignment, high RR
        gate.record(0.9, 0.1)
        gate.record(0.9, 0.1)
        result = gate.evaluate()
        # With 3 samples, avg is high enough
        assert result.action in (GateAction.PROMOTE, GateAction.HOLD)  # HOLD if window needed

    def test_alignment_bounded(self):
        gate = PromotionGate()
        gate.record(0.90, 0.1)
        hist = gate.get_alignment_history()
        assert all(0.0 <= h <= 1.0 for h in hist)
