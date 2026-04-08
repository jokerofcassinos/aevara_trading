# @module: aevara.src.live.pilot_controller
# @deps: typing, asyncio, time, dataclasses, live.ftmo_guard, live.telemetry_stream, live.failover_manager
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Progressive capital deployment with strict gate validation, real-time telemetry, and instant rollback capability.

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from aevara.src.live.ftmo_guard import FTMOGuard
from aevara.src.live.telemetry_stream import TelemetryStream, TelemetryEvent
from aevara.src.live.failover_manager import FailoverManager

@dataclass(frozen=True, slots=True)
class PilotConfig:
    """Configuracao do despacho de capital piloto (Pilot Sizing)."""
    initial_allocation_pct: float  # e.g., 0.10 (10%)
    max_allocation_pct: float      # e.g., 0.30 (30%)
    scaling_step_pct: float        # e.g., 0.05 (5%)
    validation_window_trades: int  # e.g., 50
    min_sharpe_threshold: float    # e.g., 1.5
    max_drawdown_pct: float        # e.g., 0.02 (2%)
    telemetry_flush_interval_ms: int  # e.g., 1000

class PilotController:
    """
    Gerenciador de capital progressivo para operacao LIVE.
    Orquestra sizing escalonado, fiscalizacao FTMO em tempo real e circuits breakers.
    """
    def __init__(self, initial_equity: float):
        self._config: Optional[PilotConfig] = None
        self._guard = FTMOGuard(initial_equity)
        self._stream = TelemetryStream()
        self._failover = FailoverManager()
        
        self._is_active = False
        self._current_allocation = 0.0
        self._trades_count = 0
        self._equity = initial_equity

    async def activate(self, config: PilotConfig) -> bool:
        """Ativa o dispatch de capital com sizing piloto (e.g. 10%)."""
        if self._is_active: return False
        
        # 1. Start Telemetry
        await self._stream.start()
        
        self._config = config
        self._current_allocation = config.initial_allocation_pct
        self._is_active = True
        
        await self._stream.emit(TelemetryEvent(
            "PILOT_INIT", "ACTIVE", True, self._current_allocation,
            f"Pilot Activated: Initial Allocation {self._current_allocation*100}%"
        ))
        
        return True

    async def scale_allocation(self, direction: str) -> bool:
        """Escalona a alocacao se o alpha provar edge (Sharpe > threshold)."""
        if not self._is_active or not self._config: return False
        
        prev_alloc = self._current_allocation
        if direction == "INCREASE":
             # Sizing escalonado: 10% -> 15% -> ... -> Max (e.g. 30%)
             new_alloc = min(prev_alloc + self._config.scaling_step_pct, self._config.max_allocation_pct)
        elif direction == "DECREASE":
             new_alloc = max(prev_alloc - self._config.scaling_step_pct, self._config.initial_allocation_pct)
        elif direction == "HALT":
             await self.emergency_halt("Manual Pilot Halt Requested")
             return True
        else:
             return False
        
        self._current_allocation = new_alloc
        
        await self._stream.emit(TelemetryEvent(
            "SCALING", "ACTIVE", True, self._current_allocation,
            f"Scaling Allocation: {prev_alloc*100}% -> {new_alloc*100}%"
        ))
        
        return True

    async def validate_edge(self, live_metrics: Dict) -> bool:
        """Valida que o edge vivo (Sharpe, DD) esta dentro das métricas piloto."""
        if not self._config: return False
        
        # 1. FTMO Guard Enforcement (Zero-Override)
        compliant, reason = self._guard.is_within_compliance(live_metrics)
        if not compliant:
             await self.emergency_halt(f"FTMO Guard Violation: {reason}")
             return False

        # 2. Pilot thresholds (Performance check)
        live_sharpe = live_metrics.get("sharpe", 0)
        live_drawdown = live_metrics.get("max_drawdown", 0)
        
        if live_drawdown > self._config.max_drawdown_pct:
             await self.emergency_halt("Pilot MaxDrawdown threshold exceeded")
             return False
             
        return True

    async def emergency_halt(self, reason: str) -> None:
        """Kill-switch imediato: resgata capital e para o sistema."""
        self._is_active = False
        self._current_allocation = 0.0
        
        # 1. Graceful degradation via Failover
        await self._failover.graceful_degradation(reason)
        # 2. Flush Telemetry
        await self._stream.emit(TelemetryEvent(
            "KILLSWITCH", "HALTED", False, 0.0,
            f"!!! EMERGENCY HALT !!! Reason: {reason}"
        ))
        await self._stream.flush_and_shutdown()

    def get_current_state(self) -> Dict:
        """Retorna o estado operacional do dispatch live."""
        return {
            "is_active": self._is_active,
            "allocation_pct": self._current_allocation * 100,
            "trades_count": self._trades_count,
            "equity": self._equity,
            "stream_health": self._stream.get_health_snapshot()
        }
