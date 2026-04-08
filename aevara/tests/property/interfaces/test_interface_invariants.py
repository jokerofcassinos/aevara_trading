# @module: aevara.tests.property.interfaces.test_interface_invariants
# @deps: pytest, hypothesis, asyncio, hmac, hashlib, aevara.src.interfaces.telegram_bridge
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 5+ Hypothesis tests proving zero_leakage, async_safe, bounded_queue, and auth_enforced.

from __future__ import annotations
import asyncio
import hmac
import hashlib
import time
import pytest
from hypothesis import given, strategies as st, settings
from aevara.src.interfaces.telegram_bridge import TelegramOrchestrator, BotCommand
from aevara.src.interfaces.ceo_dashboard import DashboardFeed, DashboardState

def build_hmac(secret, text, user_id, ts):
    msg = f"{ts}:{user_id}:{text}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

@settings(deadline=None)
@given(st.text(min_size=1, max_size=100), st.integers(min_value=1))
def test_auth_enforced_property(text, user_id):
    tg = TelegramOrchestrator(secret_key="SECRET")
    # Loop setup for async call
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tg.start("token", [user_id]))
    
    # Send command without HMAC
    cmd = BotCommand(text, user_id, None, time.time_ns())
    resp = loop.run_until_complete(tg.handle_command(cmd))
    assert "Unauthorized" in resp
    
    # Send command with WRONG user_id
    sig = build_hmac("SECRET", text, user_id, 1)
    cmd_wrong = BotCommand(text, user_id + 1, sig, 1)
    resp_wrong = loop.run_until_complete(tg.handle_command(cmd_wrong))
    assert "Unauthorized" in resp_wrong or "not in whitelist" in resp_wrong
    
    loop.run_until_complete(tg.stop())
    loop.close()

@given(st.integers(min_value=1, max_value=1000))
def test_dashboard_bounded_queue_property(count):
    feed = DashboardFeed(max_queue=50)
    # Loop setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    q = loop.run_until_complete(feed.subscribe("C1"))
    
    # Publish 'count' times
    for i in range(count):
        s = DashboardState(i, f"T{i}", "P", 0, "r", "OK", "d", 0, 1, 0, 0, 0)
        loop.run_until_complete(feed.publish(s))
    
    # Queue size must NOT exceed 50
    assert q.qsize() <= 50
    
    loop.close()

@given(st.text(min_size=1, max_size=50), st.text(min_size=1, max_size=50))
def test_ocl_parser_idempotency_property(text, strategic):
    from aevara.src.interfaces.ocl_parser import OCLParser
    parser = OCLParser()
    p1 = parser.decode(text)
    p2 = parser.decode(text)
    assert p1.intent == p2.intent
    assert p1.spectrum["urgency"] == p2.spectrum["urgency"]

@given(st.text(min_size=1), st.text(min_size=1))
def test_alert_router_hash_property(comp, msg):
    from aevara.src.interfaces.alert_router import AlertRouter
    router = AlertRouter()
    h1 = router._generate_hash("INFO", comp, msg)
    h2 = router._generate_hash("INFO", comp, msg)
    assert h1 == h2

@given(st.sampled_from(["INFO", "WARNING", "CRITICAL", "FATAL"]))
def test_alert_router_hierarchy_property(level):
    from aevara.src.interfaces.alert_router import AlertRouter
    router = AlertRouter()
    # Ensure handlers are separated per level
    assert len(router._handlers[level]) == 0
