# @module: aevara.tests.unit.phantom.test_scenario_generator
# @deps: aevara.src.phantom.scenario_generator
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes unitários para ScenarioGenerator: happy/edge/error/property.

from __future__ import annotations

import time
import pytest
import numpy as np
from hypothesis import given, strategies as st

from aevara.src.phantom.scenario_generator import ScenarioGenerator, PhantomScenario


# === HAPPY PATH ===
class TestScenarioGeneratorHappyPath:
    def test_generate_returns_scenario(self):
        gen = ScenarioGenerator()
        s = gen.generate("test_001")
        assert isinstance(s, PhantomScenario)
        assert s.scenario_id == "test_001"
        assert s.regime_tag in gen.REGIME_TAGS

    def test_generate_is_reproducible(self):
        gen = ScenarioGenerator()
        s1 = gen.generate("t1", seed=42)
        s2 = gen.generate("t2", seed=42)
        # Same seed -> same book values (diff IDs/timestamps)
        assert s1.book_snapshot["spread_bps"] == s2.book_snapshot["spread_bps"]

    def test_generate_with_context(self):
        gen = ScenarioGenerator()
        ctx = {"spread_bps": 5.0, "depth_imbalance": 0.3, "mid_price": 45000.0}
        s = gen.generate("ctx_test", context=ctx)
        assert s.book_snapshot["spread_bps"] >= 2.5  # context * min multiplier
        assert s.book_snapshot["mid_price"] >= 20000.0

    def test_generate_batch(self):
        gen = ScenarioGenerator()
        batch = gen.generate_batch(5, seed_start=100)
        assert len(batch) == 5
        assert all(isinstance(s, PhantomScenario) for s in batch)


# === EDGE CASES ===
class TestScenarioGeneratorEdgeCases:
    def test_crisis_regime_increases_spread(self):
        gen = ScenarioGenerator(default_seed=42)
        s = gen.generate("crisis_test", regime_tag="crisis")
        assert s.regime_tag == "crisis"
        # Crisis spread should be significantly higher than base
        assert s.book_snapshot["spread_bps"] > 3.0

    def test_choppy_regime_neutral(self):
        gen = ScenarioGenerator(default_seed=42)
        s = gen.generate("choppy_test", regime_tag="choppy")
        assert s.regime_tag == "choppy"

    def test_book_values_bounded(self):
        gen = ScenarioGenerator(default_seed=123)
        for i in range(20):
            s = gen.generate(f"bound_{i}", seed=i)
            assert 0.0 <= s.book_snapshot["spread_bps"]
            assert -1.0 <= s.book_snapshot["depth_imbalance"] <= 1.0
            assert s.book_snapshot["mid_price"] > 0.0


# === ERROR CASES ===
class TestScenarioGeneratorErrors:
    def test_empty_context_works(self):
        gen = ScenarioGenerator()
        s = gen.generate("empty_ctx")
        assert s is not None
        assert s.book_snapshot["spread_bps"] > 0.0


# === PROPERTY-BASED ===
class TestScenarioGeneratorProperties:
    @given(st.integers(min_value=1, max_value=50))
    def test_batch_size_matches_request(self, n):
        gen = ScenarioGenerator()
        batch = gen.generate_batch(n)
        assert len(batch) == n

    @given(st.integers(min_value=0, max_value=10000))
    def test_same_seed_always_same_values(self, seed):
        gen = ScenarioGenerator()
        s1 = gen.generate("s1", seed=seed)
        s2 = gen.generate("s2", seed=seed)
        assert s1.book_snapshot["spread_bps"] == s2.book_snapshot["spread_bps"]
