# @module: aevara.tests.unit.orchestrator.test_cycle_executor
# @deps: aevara.src.orchestrator.cycle_executor
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para cycle executor: async safety, handoff, timeout, retry.

from __future__ import annotations

import asyncio
import pytest
from aevara.src.orchestrator.cycle_executor import CycleExecutor, CycleResult
from aevara.src.orchestrator.qroe_engine import Phase


# === HAPPY PATH ===
class TestCycleExecutorHappyPath:
    @pytest.mark.asyncio
    async def test_execute_phase_passes(self):
        executor = CycleExecutor()
        async def success_handler():
            return {"result": "ok"}
        result = await executor.execute_phase(success_handler)
        assert result.handoff.success
        assert result.handoff.output_data == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_execute_phase_records_history(self):
        executor = CycleExecutor()
        async def handler():
            return {}
        await executor.execute_phase(handler)
        assert len(executor.get_history()) >= 1

    @pytest.mark.asyncio
    async def test_execute_phase_returns_duration(self):
        executor = CycleExecutor()
        async def handler():
            return {}
        result = await executor.execute_phase(handler)
        assert result.duration_ms >= 0


# === EDGE CASES ===
class TestCycleExecutorEdgeCases:
    @pytest.mark.asyncio
    async def test_non_dict_output_wrapped(self):
        executor = CycleExecutor()
        async def raw_handler():
            return "not_a_dict"
        result = await executor.execute_phase(raw_handler)
        assert result.handoff.output_data == {"_raw": "not_a_dict"}

    @pytest.mark.asyncio
    async def test_safe_mode_detection(self):
        executor = CycleExecutor()
        assert not executor.is_in_safe_mode()
        executor.engine.force_safe_mode(reason="Test")
        assert executor.is_in_safe_mode()

    @pytest.mark.asyncio
    async def test_safe_mode_recovery(self):
        executor = CycleExecutor()
        executor.engine.force_safe_mode(reason="Test")
        async def recovery():
            pass
        result = await executor.run_safe_mode_recovery(recovery)
        assert executor.current_phase == Phase.DISCOVERY

    @pytest.mark.asyncio
    async def test_custom_gate_results(self):
        executor = CycleExecutor()
        async def handler():
            return {}
        gates = {"G1": True, "G2": True, "G3": True, "G4": True}
        result = await executor.execute_phase(handler, gate_results=gates)
        assert result.handoff.success


# === ERROR CASES ===
class TestCycleExecutorErrors:
    @pytest.mark.asyncio
    async def test_handler_exception_triggers_safe_mode(self):
        executor = CycleExecutor()
        async def failing_handler():
            raise RuntimeError("Handler failed")
        result = await executor.execute_phase(failing_handler, timeout=30.0)
        assert result.handoff.target_phase == Phase.SAFE_MODE

    @pytest.mark.asyncio
    async def test_safe_mode_recovery_without_handler(self):
        executor = CycleExecutor()
        executor.engine.force_safe_mode(reason="Test")
        result = await executor.run_safe_mode_recovery(None)
        # Without handler, transition still occurs via get_next_phase (SAFE_MODE->DISCOVERY)
        # but no recovery was performed
        assert result.handoff.target_phase == Phase.DISCOVERY

    @pytest.mark.asyncio
    async def test_execute_phase_not_in_safe_mode_raises(self):
        executor = CycleExecutor()
        async def handler():
            pass
        with pytest.raises(ValueError, match="SAFE_MODE"):
            await executor.run_safe_mode_recovery(handler)
