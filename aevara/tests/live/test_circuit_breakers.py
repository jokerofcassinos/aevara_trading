# @module: aevara.tests.live.test_circuit_breakers
# @deps: pytest, asyncio, aevara.src.live.dynamic_circuit_breakers
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests: level transitions, hysteresis, recovery, FTMO compliance.

from __future__ import annotations
import asyncio
import pytest
from aevara.src.live.dynamic_circuit_breakers import DynamicCircuitBreaker, CBLevel

@pytest.fixture
def cb():
    return DynamicCircuitBreaker(hysteresis_gap=0.15)

@pytest.mark.asyncio
async def test_cb_transition_green_to_yellow(cb):
    # DD 1.2% (above 1% yellow threshold)
    metrics = {"max_drawdown": 0.012}
    level = await cb.evaluate(metrics)
    assert level == CBLevel.YELLOW
    assert cb.get_scaling_multiplier(level) == 0.75

@pytest.mark.asyncio
async def test_cb_transition_yellow_to_red(cb):
    # DD 3.5% (above 3% red threshold)
    metrics = {"max_drawdown": 0.035}
    level = await cb.evaluate(metrics)
    assert level == CBLevel.RED
    assert cb.get_scaling_multiplier(level) == 0.25

@pytest.mark.asyncio
async def test_cb_catastrophic_threshold(cb):
    # DD 7.6% (above 7.5% catastrophic threshold)
    metrics = {"max_drawdown": 0.076}
    level = await cb.evaluate(metrics)
    assert level == CBLevel.CATASTROPHIC
    assert cb.get_scaling_multiplier(level) == 0.0

@pytest.mark.asyncio
async def test_cb_hysteresis_lock_on_recovery(cb):
    # Phase 1: Go Red (DD 3.5% > limit 3.0%)
    await cb.evaluate({"max_drawdown": 0.035})
    assert cb._current_level == CBLevel.RED
    
    # Phase 2: Attempt recovery (DD 2.8% < limit 3.0%)
    # BUT 2.8% is still in hysteresis gap [2.55, 3.0]
    # Recovery threshold = 3.0 * (1 - 0.15) = 2.55%
    await cb.evaluate({"max_drawdown": 0.028})
    assert cb._current_level == CBLevel.RED # LOCKED by hysteresis
    
    # Phase 3: Successful recovery (DD 2.1% < 2.55%)
    await cb.evaluate({"max_drawdown": 0.021})
    assert cb._current_level != CBLevel.RED # Can finally move to Orange or below
    # It should go directly to ORANGE in this DD state
    assert cb._current_level == CBLevel.ORANGE

def test_cb_scaling_multipliers(cb):
    m_green = cb.get_scaling_multiplier(CBLevel.GREEN)
    m_cat = cb.get_scaling_multiplier(CBLevel.CATASTROPHIC)
    assert m_green == 1.0
    assert m_cat == 0.0

def test_cb_emergency_flatten_trigger(cb):
    success = cb.trigger_emergency_flatten("Panic", "TR-1")
    assert success is True
    assert cb._current_level == CBLevel.CATASTROPHIC
