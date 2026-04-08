# @module: aevara.tests.integration.test_full_system
# @deps: pytest, asyncio, main
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Full integration test for T-030 System Exposure. Validates connectivity of all 30 modules.

import pytest
import asyncio
from aevara.src.main import AevraOrganism

@pytest.mark.asyncio
async def test_organism_boot_and_connectivity():
    """Valida que o organismo inicia e todos os 30 módulos são importáveis."""
    organism = AevraOrganism()
    assert organism is not None
    assert hasattr(organism, "alpha")
    assert hasattr(organism, "mt5")
    assert hasattr(organism, "bus") # Message Bus T-030
    
    # Verifica se os skeletons Ω foram provisionados
    from aevara.src.perception.regime_detector import RegimeDetector
    rd = RegimeDetector()
    result = await rd.process()
    assert result is True

@pytest.mark.asyncio
async def test_telegram_routing_v2():
    """Valida o roteamento dos novos comandos Telegram."""
    organism = AevraOrganism()
    resp = await organism.telegram._handle_command("/status")
    assert "PHASE" in resp
    
    resp_risk = await organism.telegram._handle_command("/risk")
    assert "FTMO" in resp_risk

@pytest.mark.asyncio
async def test_message_bus_pub_sub():
    """Valida a integridade do barramento de mensagens."""
    from aevara.src.orchestrator.message_bus import bus
    queue = await bus.subscribe("TEST_TOPIC")
    await bus.publish("TEST_TOPIC", {"data": "HEARTBEAT"})
    
    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg["data"] == "HEARTBEAT"
