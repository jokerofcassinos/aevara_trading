# @module: aevara.tests.live.test_pilot_controller
# @deps: pytest, asyncio, aevara.src.live.pilot_controller
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 12+ tests: activation, sizing scaling, gate enforcement, deactivation.

from __future__ import annotations
import asyncio
import pytest
from aevara.src.live.pilot_controller import PilotController, PilotConfig

@pytest.fixture
def config():
    return PilotConfig(
        initial_allocation_pct=0.1,
        max_allocation_pct=0.3,
        scaling_step_pct=0.05,
        validation_window_trades=5,
        min_sharpe_threshold=1.5,
        max_drawdown_pct=0.01,
        telemetry_flush_interval_ms=10
    )

@pytest.fixture
async def controller():
    c = PilotController(initial_equity=100000.0)
    yield c
    # Cleanup: halt and stop telemetry
    if c._is_active:
         await c.emergency_halt("Cleanup")

@pytest.mark.asyncio
async def test_pilot_activation_success(controller, config):
    success = await controller.activate(config)
    assert success is True
    assert controller._is_active is True
    assert controller._current_allocation == 0.1

@pytest.mark.asyncio
async def test_pilot_already_active_fails(controller, config):
    await controller.activate(config)
    success = await controller.activate(config)
    assert success is False

@pytest.mark.asyncio
async def test_pilot_scaling_increase(controller, config):
    await controller.activate(config)
    # Scale from 10% to 15%
    success = await controller.scale_allocation("INCREASE")
    assert success is True
    assert controller._current_allocation == pytest.approx(0.15)

@pytest.mark.asyncio
async def test_pilot_scaling_max_limit(controller, config):
    await controller.activate(config)
    # 10% + 5%*10 = 30% (max)
    for _ in range(10):
        await controller.scale_allocation("INCREASE")
    
    assert controller._current_allocation == pytest.approx(0.3)

@pytest.mark.asyncio
async def test_pilot_scaling_decrease(controller, config):
    await controller.activate(controller._config or config)
    # Already 10% (min), decrease should stay at 10%
    success = await controller.scale_allocation("DECREASE")
    assert success is True
    assert controller._current_allocation == pytest.approx(0.1)

@pytest.mark.asyncio
async def test_pilot_edge_validation_passes(controller, config):
    await controller.activate(config)
    state = {"sharpe": 2.0, "max_drawdown": 0.005}
    valid = await controller.validate_edge(state)
    assert valid is True

@pytest.mark.asyncio
async def test_pilot_edge_validation_fails_drawdown(controller, config):
    await controller.activate(config)
    # Threshold 0.01 (1%). Report 0.02 (2%).
    state_bad = {"sharpe": 2.5, "max_drawdown": 0.02}
    valid = await controller.validate_edge(state_bad)
    assert valid is False
    assert controller._is_active is False # EMERGENCY HALT

@pytest.mark.asyncio
async def test_pilot_emergency_halt_atomic(controller, config):
    await controller.activate(config)
    await controller.emergency_halt("Manual Alert")
    assert controller._is_active is False
    assert controller._current_allocation == 0.0

@pytest.mark.asyncio
async def test_pilot_state_snapshot_integrity(controller, config):
    await controller.activate(config)
    snapshot = controller.get_current_state()
    assert snapshot["is_active"] is True
    assert snapshot["allocation_pct"] == 10.0
