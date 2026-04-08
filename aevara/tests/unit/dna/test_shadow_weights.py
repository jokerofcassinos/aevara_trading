# @module: aevara.tests.unit.dna.test_shadow_weights
# @deps: aevara.src.dna.shadow_weights
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para ShadowWeightManager: gradientes, clipping, EMA,
#           normalizacao, atomic swap, rollback.

from __future__ import annotations

import time
import pytest
import numpy as np

from aevara.src.dna.shadow_weights import ShadowWeightManager, GradientBatch, ShadowUpdate


def make_batch(grads: dict, rr: float = 1.0, alignment: float = 0.9, cycle: int = 1) -> GradientBatch:
    return GradientBatch(
        gradient_vector=grads,
        phantom_rr=rr,
        alignment_score=alignment,
        cycle_id=cycle,
        timestamp_ns=time.time_ns(),
    )


# === HAPPY PATH ===
class TestShadowWeightsHappyPath:
    def test_initialize_uniform(self):
        mgr = ShadowWeightManager()
        mgr.initialize(["A", "B", "C"])
        real = mgr._real_weights
        assert abs(sum(real.values()) - 1.0) < 1e-10
        assert all(abs(v - 1/3) < 1e-10 for v in real.values())

    def test_initialize_custom_weights(self):
        mgr = ShadowWeightManager()
        mgr.initialize(["A", "B"], {"A": 0.7, "B": 0.3})
        real = mgr.get_active_weights()
        assert abs(real["A"] - 0.7) < 1e-10
        assert abs(real["B"] - 0.3) < 1e-10

    def test_apply_gradient_updates_shadow(self):
        mgr = ShadowWeightManager(learning_rate=0.02)
        mgr.initialize(["A", "B"], {"A": 0.5, "B": 0.5})
        batch = make_batch({"A": 1.0, "B": -0.5})
        updates = mgr.apply_gradient(batch)
        assert "A" in updates
        assert updates["A"].new_shadow > updates["A"].old_shadow  # positive gradient
        assert updates["B"].new_shadow < updates["B"].old_shadow   # negative gradient

    def test_clipping_gradients(self):
        mgr = ShadowWeightManager(clip_bound=0.5)
        clipped = mgr.clip_gradients({"A": 2.0, "B": -3.0})
        assert clipped["A"] == 0.5
        assert clipped["B"] == -0.5

    def test_shadow_normalize_after_update(self):
        mgr = ShadowWeightManager(learning_rate=0.02)
        mgr.initialize(["A", "B", "C"], {"A": 0.4, "B": 0.3, "C": 0.3})
        for _ in range(20):
            batch = make_batch({"A": 0.1, "B": 0.2, "C": 0.3})
            mgr.apply_gradient(batch)
        total = sum(mgr._shadow_weights.values())
        assert abs(total - 1.0) < 1e-6

    def test_atomic_swap_increments_generation(self):
        mgr = ShadowWeightManager()
        mgr.initialize(["A", "B"])
        batch = make_batch({"A": 1.0, "B": 0.5})
        mgr.apply_gradient(batch)
        old_gen = mgr._generation
        old_real = mgr.atomic_swap()
        assert mgr._generation > old_gen

    def test_rollback_restores_weights(self):
        mgr = ShadowWeightManager()
        mgr.initialize(["A", "B"], {"A": 0.7, "B": 0.3})
        batch = make_batch({"A": 1.0, "B": 0.5})
        mgr.apply_gradient(batch)
        old = mgr.get_active_weights()
        mgr.atomic_swap()  # swap
        mgr.rollback(old)  # rollback
        restored = mgr.get_active_weights()
        assert abs(restored["A"] - 0.7) < 1e-6


# === EDGE CASES ===
class TestShadowWeightsEdgeCases:
    def test_update_unknown_agent_ignored(self):
        mgr = ShadowWeightManager()
        mgr.initialize(["A", "B"])
        batch = make_batch({"UNKNOWN": 1.0})
        updates = mgr.apply_gradient(batch)
        assert "UNKNOWN" not in updates

    def test_ema_update(self):
        mgr = ShadowWeightManager(ema_beta=0.9)
        result = mgr.ema_update({"A": 0.5}, {"A": 1.0})
        expected = 0.9 * 0.5 + 0.1 * 1.0
        assert abs(result["A"] - expected) < 1e-10

    def test_zero_learning_rate_no_change(self):
        mgr = ShadowWeightManager(learning_rate=0.0)
        mgr.initialize(["A", "B"], {"A": 0.5, "B": 0.5})
        batch = make_batch({"A": 10.0, "B": -10.0})
        mgr.apply_gradient(batch)
        # After normalization, weights should be very close to original
        total = sum(mgr._shadow_weights.values())
        assert abs(total - 1.0) < 1e-6


# === ERROR CASES ===
class TestShadowWeightsErrors:
    def test_invalid_lr_raises(self):
        with pytest.raises(AssertionError):
            ShadowWeightManager(learning_rate=-0.1)
        with pytest.raises(AssertionError):
            ShadowWeightManager(learning_rate=1.5)

    def test_invalid_clip_raises(self):
        with pytest.raises(AssertionError):
            ShadowWeightManager(clip_bound=0.0)

    def test_invalid_ema_raises(self):
        with pytest.raises(AssertionError):
            ShadowWeightManager(ema_beta=0.0)

    def test_invalid_bounds_raises(self):
        with pytest.raises(AssertionError):
            ShadowWeightManager(min_weight=0.5, max_weight=0.5)

# === PROPERTY-BASED ===
class TestShadowWeightsProperties:
    def test_weights_always_sum_to_one(self):
        mgr = ShadowWeightManager(learning_rate=0.05)
        mgr.initialize(["A", "B", "C", "D"])
        for _ in range(100):
            grads = {f"agent_{i}": np.random.randn() * 2 for i in range(4)}
            mgr.apply_gradient(make_batch(grads))
        total = sum(mgr._shadow_weights.values())
        assert abs(total - 1.0) < 1e-6
