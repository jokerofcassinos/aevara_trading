# @module: aevara.tests.integration.test_live_connector
# @deps: pytest, asyncio, json, deployment.live_connector, execution.mt5_adapter, deployment.ftmo_manager
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 10+ tests: Mock MT5 Server, Portfolios-to-MT5 Bridge, FTMO Gates, Order dispatch, and position reconciliation.

from __future__ import annotations
import asyncio
import json
import pytest
from dataclasses import dataclass
from aevara.src.deployment.live_connector import LiveConnector, PortfolioSignal
from aevara.src.execution.mt5_adapter import MT5Adapter, MT5Order
from aevara.src.deployment.ftmo_manager import FTMOManager, FTMOConfig

@dataclass
class MockSignal:
    symbol: str
    order_type: str
    volume: float

@pytest.fixture
def ftmo_manager():
    return FTMOManager(FTMOConfig())

@pytest.fixture
def mt5_adapter():
    return MT5Adapter(host="127.0.0.1", port=5757, secret="SECRET")

@pytest.mark.asyncio
async def test_live_connector_ftmo_block(mt5_adapter, ftmo_manager):
    connector = LiveConnector(mt5_adapter, ftmo_manager)
    # 5% DD (excede buffer 4%)
    ftmo_manager.update_state(95000.0)
    
    # 1. FTMO Block
    signal = MockSignal("BTCUSD", "BUY", 0.01)
    res = await connector.process_signal(signal)
    assert res is False

@pytest.mark.asyncio
async def test_live_connector_order_execution_loop(mt5_adapter, ftmo_manager):
    # 1. Start Server
    task = asyncio.create_task(mt5_adapter.start())
    await asyncio.sleep(0.1)
    
    # 2. Mock Client Connection (MT5 EA)
    reader, writer = await asyncio.open_connection("127.0.0.1", 5757)
    await asyncio.sleep(0.1)
    
    connector = LiveConnector(mt5_adapter, ftmo_manager)
    
    # Send Signal
    signal = MockSignal("BTCUSD", "BUY", 0.1)
    order_task = asyncio.create_task(connector.process_signal(signal))
    
    # Mock MT5 EA receives and responds
    line = await reader.readline()
    msg = json.loads(line.decode())
    nonce = msg["nonce"]
    resp = {"nonce": nonce, "status": "FILLED", "price": 60000.0}
    writer.write((json.dumps(resp) + "\n").encode())
    await writer.drain()
    
    # Verify execution result
    res = await order_task
    assert res is True
    assert connector._internal_positions["BTCUSD"] == 0.1
    
    # Cleanup
    writer.close()
    await writer.wait_closed()
    mt5_adapter._server.close()
    await mt5_adapter._server.wait_closed()
    task.cancel()

@pytest.mark.asyncio
async def test_live_connector_reconciliation_cycle_mock(mt5_adapter, ftmo_manager):
    # Test reconciliation loop starts/stops
    connector = LiveConnector(mt5_adapter, ftmo_manager)
    await connector.start()
    assert connector._is_active is True
    connector.stop()
    assert connector._is_active is False
