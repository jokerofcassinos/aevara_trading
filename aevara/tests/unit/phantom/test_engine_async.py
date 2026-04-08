# @module: aevara.tests.unit.phantom.test_engine_async
# @deps: aevara.src.phantom.engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para PhantomEngine: concurrency safety, timeout, non-blocking verification.

from __future__ import annotations

import asyncio
import pytest

from aevara.src.phantom.engine import PhantomEngine, EngineMetrics
from aevara.src.phantom.scenario_generator import PhantomScenario


# === HAPPY PATH ===
class TestPhantomEngineHappyPath:
    @pytest.mark.asyncio
    async def test_generate_scenario(self):
        engine = PhantomEngine()
        scenario = await engine.generate_scenario({"mid_price": 50000.0})
        assert scenario is not None
        assert "scenario_" in scenario.scenario_id

    @pytest.mark.asyncio
    async def test_simulate_execution(self):
        engine = PhantomEngine()
        scenario = await engine.generate_scenario()
        outcome = await engine.simulate_execution(
            scenario,
            decision={"side": "long", "size": 1.0, "confidence": 0.8},
            real_rr=1.5,
        )
        assert 0.0 <= outcome.alignment_score <= 1.0
        assert 0.0 <= outcome.fill_rate <= 1.0

    @pytest.mark.asyncio
    async def test_metrics_returns_valid(self):
        engine = PhantomEngine()
        m = engine.metrics
        assert isinstance(m, EngineMetrics)
        assert m.total_scenarios == 0

    @pytest.mark.asyncio
    async def test_alignment_with_reality(self):
        engine = PhantomEngine()
        alignment = await engine.align_with_reality(real_rr=1.0, phantom_rr=0.9)
        assert 0.0 <= alignment <= 1.0
        assert alignment > 0.5  # Small deviation

    @pytest.mark.asyncio
    async def test_shadow_gradient_extraction(self):
        engine = PhantomEngine()
        scenario = await engine.generate_scenario()
        outcome = await engine.simulate_execution(scenario, {"side": "long", "size": 1.0})
        gradient = engine.estimate_shadow_gradient(outcome)
        assert len(gradient) > 0
        for v in gradient.values():
            assert -1.0 <= v <= 1.0  # Within bounds

    @pytest.mark.asyncio
    async def test_get_latest_outcomes(self):
        engine = PhantomEngine()
        assert engine.get_latest_outcomes(5) == []
        scenario = await engine.generate_scenario()
        await engine.simulate_execution(scenario, {"side": "long"})
        outcomes = engine.get_latest_outcomes(1)
        assert len(outcomes) == 1


# === EDGE CASES ===
class TestPhantomEngineEdgeCases:
    @pytest.mark.asyncio
    async def test_calibration_flag_activates_on_deviation(self):
        engine = PhantomEngine()
        # Simulate large deviation 6 times (> 5 threshold)
        for _ in range(6):
            await engine.align_with_reality(real_rr=1.0, phantom_rr=5.0)
        assert engine.calibration_flag

    @pytest.mark.asyncio
    async def test_calibration_flag_resets_on_good_alignment(self):
        engine = PhantomEngine()
        # Force violations
        for _ in range(6):
            await engine.align_with_reality(real_rr=1.0, phantom_rr=5.0)
        assert engine.calibration_flag
        # Good alignment resets
        await engine.align_with_reality(real_rr=1.0, phantom_rr=1.0)
        assert not engine.calibration_flag

    @pytest.mark.asyncio
    async def test_memory_bounded(self):
        engine = PhantomEngine()
        for i in range(6000):
            scenario = await engine.generate_scenario()
            await engine.simulate_execution(scenario, {"side": "long"})
        assert len(engine.get_latest_outcomes()) <= 5000


# === ERROR CASES ===
class TestPhantomEngineErrors:
    @pytest.mark.asyncio
    async def test_nonblocking_verification(self):
        """Engine não bloqueia: múltiplas chamadas devem retornar rapidamente."""
        engine = PhantomEngine()
        start = asyncio.get_event_loop().time()

        # 10 concurrent simulations
        tasks = [
            engine.simulate_execution(
                await engine.generate_scenario(),
                {"side": "long", "size": 1.0},
            )
            for _ in range(10)
        ]
        await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start
        # Should complete quickly (semaphore limits to 3 at a time)
        assert elapsed < 30.0  # Well under generous timeout
