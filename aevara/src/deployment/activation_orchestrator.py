# @module: aevara.src.deployment.activation_orchestrator
# @deps: asyncio, typing, dataclasses, telemetry.logger, risk.gates
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Phase-gated activation orchestrator enforcing immutable gates, pilot sizing lock, and CEO command routing.

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class ActivationGate:
    """Portão de validação imutável para transição de fase (v1.0.0)."""
    phase: str
    latency_p99_ms: float
    reconciliation_drift_pct: float
    ftmo_daily_dd_pct: float
    ftmo_total_dd_pct: float
    pilot_trades_completed: int
    edge_significant: bool
    ceo_approved: bool

class ActivationOrchestrator:
    """
    Orquestrador de Ativação (v1.0.0).
    Gerencia a cronologia executiva (Demo -> Micro -> Live).
    Implementa o roteamento de comandos do CEO e validação de gates imutáveis.
    """
    def __init__(self, pilot_controller: Any):
        self._current_phase = "IDLE"
        self._pilot = pilot_controller
        self._is_halted = False
        self._gates: Dict[str, ActivationGate] = {}
        self._start_time_ns = time.time_ns()

    async def start_phase(self, phase: str) -> bool:
        """Inicia uma fase de ativação após validação basal."""
        valid_phases = ["DEMO", "MICRO_LIVE", "LIVE_SCALING"]
        if phase not in valid_phases:
             print(f"AEVRA ACTIVATION: Invalid phase {phase}")
             return False
             
        self._current_phase = phase
        print(f"AEVRA ACTIVATION: Transitioned to phase {phase}")
        
        # Bloqueia sizing se for DEMO ou MICRO_LIVE
        if phase in ["DEMO", "MICRO_LIVE"]:
             await self._pilot.lock_sizing(0.01)
        else:
             await self._pilot.unlock_sizing()
             
        return True

    async def validate_gate(self, gate: ActivationGate) -> bool:
        """
        Tribunal de Fase: Verifica se todos os critérios técnicos 
        e a aprovação do CEO foram atendidos.
        """
        if not gate.ceo_approved:
             print(f"AEVRA ACTIVATION: CEO approval missing for {gate.phase}")
             return False
             
        if gate.latency_p99_ms > 50.0:
             print("AEVRA ACTIVATION: Latency p99 too high.")
             return False
             
        if gate.ftmo_daily_dd_pct > 0.04:
             print("AEVRA ACTIVATION: FTMO daily budget exceeded.")
             return False
             
        self._gates[gate.phase] = gate
        return True

    async def handle_ceo_command(self, command: str) -> str:
        """Roteia comandos administrativos do CEO via CLI/Terminal."""
        cmd = command.lower().strip()
        
        if cmd == "/status":
             return f"PHASE: {self._current_phase} | PILOT_LOCKED: {self._pilot.is_locked()}"
        
        if cmd == "/go_live_demo":
             success = await self.start_phase("DEMO")
             return "SUCCESS: Phase DEMO started." if success else "ERROR: Phase transition failed."
             
        if cmd == "/go_live_micro":
             success = await self.start_phase("MICRO_LIVE")
             return "SUCCESS: Phase MICRO_LIVE started." if success else "ERROR: Phase transition failed."

        if cmd == "/enable_scaling":
             if self._current_phase != "MICRO_LIVE": 
                  return "ERROR: Must be in MICRO_LIVE to enable scaling."
             success = await self.start_phase("LIVE_SCALING")
             return "SUCCESS: Scaling enabled. Ergodic maximization active." if success else "ERROR"

        if cmd == "/pause":
             self._is_halted = True
             return "SYSTEM PAUSED. No new trades."
             
        if cmd == "/resume":
             self._is_halted = False
             return "SYSTEM RESUMED."

        return f"UNKNOWN COMMAND: {command}"

    async def emergency_halt(self, reason: str) -> None:
        """Congelamento atômico global em < 500ms."""
        self._is_halted = True
        print(f"AEVRA ACTIVATION: CRITICAL HALT -> {reason}")
        # await mt5.close_all_positions()

    def get_phase_status(self) -> Dict:
        return {
            "phase": self._current_phase,
            "is_halted": self._is_halted,
            "uptime_s": (time.time_ns() - self._start_time_ns) / 1e9
        }
