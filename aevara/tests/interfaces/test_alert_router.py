# @module: aevara.tests.interfaces.test_alert_router
# @deps: pytest, asyncio, aevara.src.interfaces.alert_router
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 8+ tests for alert router: dedup, escalation, suppression, and quiet hours.

from __future__ import annotations
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from aevara.src.interfaces.alert_router import AlertRouter

@pytest.fixture
def router():
    return AlertRouter(dedup_window_s=1)

@pytest.mark.asyncio
async def test_dedup_suppression(router):
    handler = AsyncMock()
    router.register_handler("WARNING", handler)
    
    # 1. First alert should route
    await router.route("WARNING", "Engine", "Overheat")
    assert handler.call_count == 1
    
    # 2. Second alert within 1s should be suppressed
    await router.route("WARNING", "Engine", "Overheat")
    assert handler.call_count == 1

@pytest.mark.asyncio
async def test_escalation_logic(router):
    # After 11 alerts, it should become CRITICAL if we manually set counts
    # But router increments counts during suppression
    # To test escalation, we check the helper
    alert_hash = router._generate_hash("WARNING", "X", "Y")
    router._alert_counts[alert_hash] = 11
    assert router.escalate(alert_hash) == "CRITICAL"
    
    router._alert_counts[alert_hash] = 51
    assert router.escalate(alert_hash) == "FATAL"

@pytest.mark.asyncio
async def test_quiet_hours_suppression(router):
    handler = AsyncMock()
    router.register_handler("INFO", handler)
    
    # Set quiet hours to cover current time (Simulation)
    # We mock _is_quiet_hour for deterministic test
    router._is_quiet_hour = lambda: True
    
    await router.route("INFO", "Sys", "Heartbeat")
    assert handler.call_count == 0 # Suppressed during quiet hours
    
    # CRITICAL should still pass
    router.register_handler("CRITICAL", handler)
    await router.route("CRITICAL", "Sys", "BOOM")
    assert handler.call_count == 1

@pytest.mark.asyncio
async def test_multiple_handlers(router):
    h1 = AsyncMock()
    h2 = MagicMock()
    
    router.register_handler("WARNING", h1)
    router.register_handler("WARNING", h2)
    
    await router.route("WARNING", "Mod", "Msg")
    assert h1.call_count == 1
    assert h2.call_count == 1

@pytest.mark.asyncio
async def test_context_propagation(router):
    handler = AsyncMock()
    router.register_handler("INFO", handler)
    ctx = {"id": 123}
    await router.route("INFO", "C", "M", ctx)
    
    # Check if context was passed
    args, kwargs = handler.call_args
    assert args[2] == ctx

@pytest.mark.asyncio
async def test_alert_hash_consistency(router):
    h1 = router._generate_hash("A", "B", "C")
    h2 = router._generate_hash("A", "B", "C")
    assert h1 == h2
    assert h1 != router._generate_hash("A", "B", "D")

@pytest.mark.asyncio
async def test_dedup_counter_in_message(router):
    handler = AsyncMock()
    router.register_handler("WARNING", handler)
    
    await router.route("WARNING", "Mod", "Msg")
    # Suppress next and check counter (internally it would be in message if we didn't mock)
    # But router increments count
    h = router._generate_hash("WARNING", "Mod", "Msg")
    await router.route("WARNING", "Mod", "Msg")
    assert router._alert_counts[h] == 2

@pytest.mark.asyncio
async def test_invalid_handler_isolation(router):
    # Crashy handler should not stop other handlers
    h1 = MagicMock(side_effect=Exception("BOOM"))
    h2 = AsyncMock()
    
    router.register_handler("CRITICAL", h1)
    router.register_handler("CRITICAL", h2)
    
    await router.route("CRITICAL", "Sys", "Err")
    assert h2.call_count == 1
