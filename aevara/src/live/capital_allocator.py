# @module: aevara.src.live.capital_allocator
# @deps: typing, asyncio, time, live.adaptive_scaling_engine, live.live_edge_monitor
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Progressive capital deployment scheduler with validation gates and risk-reward optimization.

from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from aevara.src.live.adaptive_scaling_engine import AdaptiveScalingEngine, ScalingConfig, SizingDecision
from aevara.src.live.live_edge_monitor import LiveEdgeMonitor

class CapitalAllocator:
    """
    Scheduler progressivo de alocação de capital (Growth Engine).
    Garante que o organismo expanda de 10% a 100% de forma determinística
    somente após validação de edge vivo.
    """
    def __init__(self, config: ScalingConfig):
        self._engine = AdaptiveScalingEngine(config)
        self._monitor = LiveEdgeMonitor(window_size=config.validation_window)
        self._config = config
        
        self._current_level = 0
        self._levels = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0] # Escalonamento
        self._trades_count = 0
        self._is_scaling_locked = False

    async def add_trade_and_evaluate(self, 
                                     ret_pct: float, 
                                     pnl: float, 
                                     context: Dict) -> Tuple[float, Optional[str]]:
        """
        Recebe resultado do trade, atualiza monitor e reavalia nível de alocação.
        Retorna (nova_alocacao_pct, motivo_se_mudou).
        """
        self._monitor.add_trade(ret_pct, pnl)
        self._trades_count += 1
        
        metrics = self._monitor.get_metrics()
        current_alloc = self._levels[self._current_level]
        
        # 1. Check Scaling Gates (UP)
        if self._trades_count >= self._config.validation_window and not self._is_scaling_locked:
            sharpe = metrics["sharpe"]
            conf = metrics["significance"]
            
            if sharpe >= self._config.min_edge_sharpe and conf >= 0.90:
                 if self._current_level < len(self._levels) - 1:
                      # Step UP: Upgrade capital deployment level
                      self._current_level += 1
                      self._trades_count = 0 # Reset window for next level
                      new_alloc = self._levels[self._current_level]
                      return new_alloc, f"UPGRADE: Sharpe {sharpe:.2f} | Confidence {conf:.2f}"

        # 2. Check Degradation (DOWN)
        if metrics["sharpe"] < (self._config.min_edge_sharpe * 0.5): # 50% drop
             if self._current_level > 0:
                  self._current_level -= 1
                  new_alloc = self._levels[self._current_level]
                  return new_alloc, f"DOWNGRADE: Edge decay (Sharpe {metrics['sharpe']:.2f})"

        return current_alloc, None

    def get_allocation_pct(self) -> float:
        return self._levels[self._current_level]

    def lock_scaling(self, reason: str) -> None:
        """Bloqueia escalonamento progressivo (freeze capital tier)."""
        self._is_scaling_locked = True

    def unlock_scaling(self) -> None:
        self._is_scaling_locked = False
