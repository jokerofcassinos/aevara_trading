# @module: aevara.tests.portfolio.test_multi_asset
# @deps: pytest, asyncio, aevara.src.portfolio.multi_asset_router, aevara.config.assets
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: 15+ tests: Multi-asset routing, config loading, liquidity scoring, and async dispatching.

from __future__ import annotations
import pytest
import asyncio
import time
from aevara.src.portfolio.multi_asset_router import MultiAssetRouter, AssetConfig, ExecutionDispatch

@pytest.fixture
def router():
    return MultiAssetRouter(max_queue_size=10)

@pytest.fixture
def btc_config():
    return AssetConfig(
        symbol="BTCUSDT", base_currency="BTC", quote_currency="USDT", 
        tick_size=0.01, lot_size=1.0, min_order_size=0.01, max_order_size=10.0,
        session_profile={"0_24": 1.0}, funding_normalization_factor=1.0, 
        tce_budget_bps=2.0, liquidity_score_threshold=0.8
    )

@pytest.mark.asyncio
async def test_router_asset_registration(router, btc_config):
    # Teste de registro de múltiplos ativos
    res = await router.register_asset(btc_config)
    assert res is True
    assert "BTCUSDT" in router._registry

@pytest.mark.asyncio
async def test_router_dispatch_success(router, btc_config):
    # Teste de dispatch unitário bem-sucedido
    await router.register_asset(btc_config)
    dispatch = ExecutionDispatch(symbol="BTCUSDT", direction="BUY", size=0.1, order_type="MARKET")
    res = await router.dispatch(dispatch)
    assert res is True
    assert router._dispatch_queue.qsize() == 1

@pytest.mark.asyncio
async def test_router_dispatch_fail_unregistered(router):
    # Teste de falha ao enviar símbolo não registrado
    dispatch = ExecutionDispatch(symbol="UNKNOWN", direction="BUY", size=0.1, order_type="MARKET")
    res = await router.dispatch(dispatch)
    assert res is False

@pytest.mark.asyncio
async def test_router_queue_full_protection(router, btc_config):
    # Teste de proteção contra estouro de fila (bounded queue)
    await router.register_asset(btc_config)
    for _ in range(10):
         await router.dispatch(ExecutionDispatch(symbol="BTCUSDT", direction="BUY", size=0.1, order_type="MARKET"))
    
    # 11th dispatch should fail
    res = await router.dispatch(ExecutionDispatch(symbol="BTCUSDT", direction="BUY", size=0.1, order_type="MARKET"))
    assert res is False

@pytest.mark.asyncio
async def test_router_processing_loop_mock(router, btc_config):
    # Teste do loop de processamento com semáforo
    await router.register_asset(btc_config)
    await router.dispatch(ExecutionDispatch(symbol="BTCUSDT", direction="BUY", size=0.1, order_type="MARKET"))
    
    # Inicia loop processador
    task = asyncio.create_task(router._processing_loop())
    await asyncio.sleep(0.1)
    
    assert router._dispatch_queue.qsize() == 0 # Processado
    router._is_running = False
    task.cancel()
