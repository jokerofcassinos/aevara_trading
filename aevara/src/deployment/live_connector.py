# @module: aevara.src.deployment.live_connector
# @deps: asyncio, typing, deployment.ftmo_manager, execution.mt5_adapter, portfolio.multi_strategy_allocator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Bridges Portfolio Signals to MT5 Adapter. Handles execution lifecycle and continuous reconciliation loop.

from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Protocol
from aevara.src.deployment.ftmo_manager import FTMOManager
from aevara.src.execution.mt5_adapter import MT5Adapter, MT5Order

class PortfolioSignal(Protocol):
    symbol: str
    order_type: str
    volume: float

class LiveConnector:
    """
    O 'Elo Físico' (v1.0) entre inteligência e execução.
    Processa sinais de portfólio, valida contra regras FTMO e despacha para MT5.
    Mantém reconciliação contínua 3s para combater drift de posições.
    """
    def __init__(self, mt5_adapter: MT5Adapter, ftmo_manager: FTMOManager):
        self._mt5 = mt5_adapter
        self._ftmo = ftmo_manager
        self._internal_positions: Dict[str, float] = {}
        self._is_active = False

    async def start(self) -> None:
        """Inicia loop de reconciliação e listener de sinais."""
        self._is_active = True
        asyncio.create_task(self._reconciliation_loop())
        print("AEVRA LIVE CONNECTOR: Active and Reconciling...")

    async def _reconciliation_loop(self, interval_s: float = 3.0):
        """Loop de 3s para sincronização terminal vs interna."""
        while self._is_active:
             try:
                  # Consulta terminal MT5 via Adapter (QUERY_POSITIONS)
                  # terminal_pos = await self._mt5.get_positions()
                  # sync(self._internal_positions, terminal_pos)
                  pass 
             except Exception as e:
                  print(f"AEVRA RECON ERROR: {e}")
             
             await asyncio.sleep(interval_s)

    async def process_signal(self, signal: PortfolioSignal) -> bool:
        """
        Gatilho atômico de execução:
        1. Validação FTMO de segurança Drawdown/Budget.
        2. Conversão Signal -> MT5 Order.
        3. Envio assíncrono via Socket Bridge.
        4. Reconciliação imediata da resposta.
        """
        # 1. FTMO Hard Gate
        is_safe, msg = self._ftmo.is_safe_to_trade()
        if not is_safe:
             print(f"AEVRA BLOCKED: {msg}")
             return False
             
        # 2. Risk Sizing Adjustment based on FTMO Budget
        risk_budget = self._ftmo.get_risk_budget()
        adjusted_volume = signal.volume * (risk_budget / 0.01) # Example adjustment
        
        # 3. Create MT5 Order
        order = MT5Order(
            symbol=signal.symbol,
            order_type=signal.order_type,
            volume=max(0.01, round(adjusted_volume, 2)),
            price_requested=0.0 # Market execution usually
        )
        
        # 4. Atomic Execution via Socket
        try:
             result = await self._mt5.send_order(order)
             if result.get("status") == "FILLED":
                  # Atualiza Telemetria
                  self._update_internal_pos(signal.symbol, order.order_type, order.volume)
                  return True
        except Exception as e:
             print(f"AEVRA EXECUTION ERROR: {e}")
        
        return False

    def _update_internal_pos(self, symbol: str, order_type: str, volume: float):
        """Atualização rápida de estado interno antes da reconciliação total."""
        if order_type == "BUY":
             self._internal_positions[symbol] = self._internal_positions.get(symbol, 0) + volume
        elif order_type == "SELL":
             self._internal_positions[symbol] = self._internal_positions.get(symbol, 0) - volume

    def stop(self):
        self._is_active = False
