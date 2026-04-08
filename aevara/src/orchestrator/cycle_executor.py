# @module: aevara.src.orchestrator.cycle_executor
# @deps: aevara.src.orchestrator.qroe_engine, aevara.src.orchestrator.profile_router
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Async cycle loop, handoff management, timeout handling, and
#           graceful degradation. Orchestrates QROE phases with async-first
#           execution, zero blocking, and graceful fallback to SAFE_MODE.

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional
from aevara.src.orchestrator.qroe_engine import (
    QROEEngine,
    Phase,
    StateTransition,
    CycleState,
)
from aevara.src.orchestrator.profile_router import ProfileRouter

CYCLE_TIMEOUT = 30.0  # seconds


@dataclass(frozen=True, slots=True)
class HandoffResult:
    """Resultado de handoff entre fases."""
    source_phase: Phase
    target_phase: Phase
    success: bool
    output_data: Optional[Dict[str, Any]]
    detail: str


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Resultado de um ciclo completo."""
    cycle_id: int
    phase: Phase
    transition: StateTransition
    handoff: HandoffResult
    duration_ms: float
    error: str = ""


class CycleExecutor:
    """
    Loop assincrono de execucao QROE.

    Invariantes:
    - Zero chamadas sincronas no hot path
    - Timeout em 30s -> SAFE_MODE
    - Handoff atomico: falha = rollback
    - Graceful degradation: se fase nao puder executar -> SAFE_MODE
    """

    def __init__(self, engine: Optional[QROEEngine] = None, router: Optional[ProfileRouter] = None):
        self._engine = engine or QROEEngine()
        self._router = router or ProfileRouter()
        self._history: List[CycleResult] = []

    @property
    def engine(self) -> QROEEngine:
        return self._engine

    @property
    def current_phase(self) -> Phase:
        return self._engine.current_phase

    async def execute_phase(
        self,
        handler: Callable[[], Coroutine[None, None, Dict[str, Any]]],
        gate_results: Optional[Dict[str, bool]] = None,
        timeout: float = CYCLE_TIMEOUT,
    ) -> CycleResult:
        """
        Executa handler assincrono para fase atual.

        Args:
            handler: Coroutine que retorna output da fase
            gate_results: Resultados dos gates (default: all pass)
            timeout: Maximo tempo de execucao em segundos

        Returns:
            CycleResult com resultado completo
        """
        phase = self._engine.current_phase
        start_ms = time.time() * 1000

        # Allocate profile
        cycle_id = self._engine.cycle_id
        profile_id, alloc = self._router.allocate(phase, cycle_id)

        gates = gate_results or StateTransition.all_gates_pass()

        # Execute with timeout
        try:
            output = await asyncio.wait_for(handler(), timeout=timeout)

            # Validate output contract
            if not isinstance(output, dict):
                output = {"_raw": output}

            # Transition to next phase
            transition = self._engine.execute_transition(gates)

            # Create handoff
            handoff = HandoffResult(
                source_phase=phase,
                target_phase=transition.to_phase if transition.is_valid() else phase,
                success=transition.is_valid(),
                output_data=output,
                detail=f"Phase {phase.name} completed" if transition.is_valid() else f"Phase stuck: {transition.get_failed_gates()}",
            )

        except asyncio.TimeoutError:
            transition = self._engine.force_safe_mode(
                reason=f"Phase {phase.name} timed out after {timeout}s"
            )
            handoff = HandoffResult(
                source_phase=phase,
                target_phase=Phase.SAFE_MODE,
                success=False,
                output_data=None,
                detail=f"Timeout: {timeout}s exceeded",
            )
        except Exception as e:
            transition = self._engine.force_safe_mode(
                reason=f"Phase {phase.name} error: {e}"
            )
            handoff = HandoffResult(
                source_phase=phase,
                target_phase=Phase.SAFE_MODE,
                success=False,
                output_data=None,
                detail=f"Error: {e}",
            )

        duration_ms = (time.time() * 1000) - start_ms

        result = CycleResult(
            cycle_id=self._engine.cycle_id,
            phase=phase,
            transition=transition,
            handoff=handoff,
            duration_ms=duration_ms,
        )
        self._history.append(result)
        return result

    async def run_safe_mode_recovery(
        self,
        recovery_handler: Optional[Callable[[], Coroutine[None, None, None]]] = None,
    ) -> CycleResult:
        """
        Executa recuperacao em SAFE_MODE.
        Se recovery_handler passar, volta para DISCOVERY.
        """
        if self._engine.current_phase != Phase.SAFE_MODE:
            raise ValueError("Can only run safe mode recovery when in SAFE_MODE")

        start_ms = time.time() * 1000
        transition = self._engine.execute_transition(StateTransition.all_gates_pass())

        if recovery_handler:
            try:
                await asyncio.wait_for(recovery_handler(), timeout=CYCLE_TIMEOUT)
                self._engine.reset_to_discovery()
            except Exception:
                pass  # Stay in SAFE_MODE

        handoff = HandoffResult(
            source_phase=Phase.SAFE_MODE,
            target_phase=self._engine.current_phase,
            success=self._engine.current_phase != Phase.SAFE_MODE,
            output_data=None,
            detail="Safe mode recovery executed" if self._engine.current_phase != Phase.SAFE_MODE else "Safe mode persists",
        )
        duration_ms = (time.time() * 1000) - start_ms

        result = CycleResult(
            cycle_id=self._engine.cycle_id,
            phase=Phase.SAFE_MODE,
            transition=transition,
            handoff=handoff,
            duration_ms=duration_ms,
        )
        self._history.append(result)
        return result

    def get_history(self) -> List[CycleResult]:
        return list(self._history)

    def is_in_safe_mode(self) -> bool:
        return self._engine.current_phase == Phase.SAFE_MODE
