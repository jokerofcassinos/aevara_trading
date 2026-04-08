# @module: aevara.tests.interfaces.test_telegram
# @deps: pytest, asyncio, hmac, hashlib, aevara.src.interfaces.telegram_bridge
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests for telegram bot: auth, routing, rate limit, error handling, HMAC validation.

from __future__ import annotations
import asyncio
import hmac
import hashlib
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from aevara.src.interfaces.telegram_bridge import TelegramOrchestrator, BotCommand

@pytest.fixture
async def tg():
    orchestrator = TelegramOrchestrator(secret_key="SECRET")
    yield orchestrator
    await orchestrator.stop()

def sign(text, user_id, timestamp, secret="SECRET"):
    msg = f"{timestamp}:{user_id}:{text}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

@pytest.mark.asyncio
async def test_unauthorized_hmac(tg):
    await tg.start("token", [12345])
    cmd = BotCommand("status", 12345, "bad-hash", time.time_ns())
    resp = await tg.handle_command(cmd)
    assert "Unauthorized" in resp

@pytest.mark.asyncio
async def test_authorized_command(tg):
    user_id = 999
    await tg.start("token", [user_id])
    ts = time.time_ns()
    text = "status"
    signature = sign(text, user_id, ts, "SECRET")
    
    cmd = BotCommand(text, user_id, signature, ts)
    resp = await tg.handle_command(cmd)
    
    assert "Intent: QUERY" in resp # OCL Parser decodes "status" as QUERY
    assert "Urgency:" in resp

@pytest.mark.asyncio
async def test_user_not_whitelisted(tg):
    ts = time.time_ns()
    text = "status"
    # Even if signature is valid, user_id must be in whitelist
    signature = sign(text, 555, ts, "SECRET")
    
    await tg.start("token", [12345]) # different ID
    cmd = BotCommand(text, 555, signature, ts)
    resp = await tg.handle_command(cmd)
    
    assert "not in whitelist" in resp

@pytest.mark.asyncio
async def test_intent_parsing_oce_te(tg):
    # Test strategic intent extraction
    user_id = 123
    await tg.start("token", [user_id])
    ts = time.time_ns()
    text = "mudar daily loss 5% urgente!"
    signature = sign(text, user_id, ts, "SECRET")
    
    cmd = BotCommand(text, user_id, signature, ts)
    resp = await tg.handle_command(cmd)
    
    assert "Intent: THRESHOLD_UPDATE" in resp
    assert "Params: {'value_pct': 5.0}" in resp or "{'value_pct': 5}" in resp

@pytest.mark.asyncio
async def test_async_alert_pushing(tg):
    await tg.start("token", [123])
    # Queue should non-blockingly accept alerts
    passed = await tg.push_alert("CRITICAL", "Test Alert")
    assert passed is True
    assert tg._pending_alerts.qsize() == 1
    
    # Check rate limit/pusher loop (wait briefly)
    await asyncio.sleep(0.02)
    # The loop should have processed the alert
    assert tg._pending_alerts.qsize() == 0

@pytest.mark.parametrize("input_text,expected_intent", [
    ("como esta o sistema", "QUERY"),
    ("pausar operacoes", "PAUSE"),
    ("voltar a rodar", "RESUME"),
    ("configurar daily loss 4%", "THRESHOLD_UPDATE"),
    ("size 0.5", "THRESHOLD_UPDATE"),
    ("ajuda", "UNKNOWN")
])
@pytest.mark.asyncio
async def test_ocl_intent_matrix(tg, input_text, expected_intent):
    user_id = 123
    await tg.start("token", [user_id])
    ts = time.time_ns()
    sig = sign(input_text, user_id, ts, "SECRET")
    cmd = BotCommand(input_text, user_id, sig, ts)
    resp = await tg.handle_command(cmd)
    
    if expected_intent == "UNKNOWN":
        assert "Intent ambiguous" in resp
    else:
        assert f"Intent: {expected_intent}" in resp

@pytest.mark.asyncio
async def test_tg_orchestrator_stop(tg):
    await tg.start("t", [12])
    await tg.stop()
    assert tg._is_running is False

@pytest.mark.asyncio
async def test_alert_queue_full_drop(tg):
    tg._is_running = True # manually set to speed up
    # maxsize is 1000, we mock it to 2
    tg._pending_alerts = asyncio.Queue(maxsize=2)
    await tg.push_alert("A", "M1")
    await tg.push_alert("A", "M2")
    await tg.push_alert("A", "M3") # should drop M1
    assert tg._pending_alerts.qsize() == 2
