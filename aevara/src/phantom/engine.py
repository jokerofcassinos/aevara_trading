# @module: aevara.src.phantom.engine
# @deps: aevara.src.phantom.scenario_generator, aevara.src.phantom.execution_simulator, aevara.src.memory.context_library, aevara.src.orchestrator.qroe_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Async contrafactual simulation engine with RealityAnchor protocol,
#           shadow gradient estimation, bounded memory ring buffer, and
#           non-blocking background loop. Não bloqueia hot path.

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from aevara.src.phantom.scenario_generator import PhantomScenario, ScenarioGenerator
from aevara.src.phantom.execution_simulator import ExecutionSimulator, PhantomOutcome


ALIGNMENT_THRESHOLD = 0.82
CALIBRATION_DEVIATION = 0.15
MAX_CALIBRATION_CYCLES = 5
OUTCOME_BUFFER_CAPACITY = 5000


@dataclass(frozen=True, slots=True)
class EngineMetrics:
    """Métricas de saúde do PhantomEngine."""
    total_scenarios: int
    avg_alignment: float
    calibration_flag: bool
    buffer_usage: float       # 0-1
    last_alignment: float


class PhantomEngine:
    """
    Motor de simulação contrafactual assíncrono.

    Invariantes:
    - Geração e simulação são non-blocking (asyncio.Semaphore limita concorrência)
    - Ring buffer de outcomes bounded (capacity=5000)
    - |RR_phantom - RR_real| > 0.15 por >5 ciclos ativa calibration_flag
    - Gradientes clipados e regularizados
    - Reprodutibilidade via seed
    """

    def __init__(
        self,
        seed: int = 42,
        max_concurrency: int = 3,
        scenario_buffer: int = OUTCOME_BUFFER_CAPACITY,
    ):
        self._generator = ScenarioGenerator(default_seed=seed)
        self._simulator = ExecutionSimulator()
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._outcome_buffer: deque[PhantomOutcome] = deque(maxlen=scenario_buffer)
        self._alignment_history: deque[Tuple[float, float]] = deque(maxlen=100)
        self._calibration_counter = 0
        self._calibration_flag = False
        self._total_scenarios = 0
        self._running = False
        self._background_task: Optional[asyncio.Task] = None

    @property
    def calibration_flag(self) -> bool:
        return self._calibration_flag

    @property
    def metrics(self) -> EngineMetrics:
        if not self._alignment_history:
            avg = 0.0
        else:
            avg = sum(a for a, _ in self._alignment_history) / len(self._alignment_history)
        return EngineMetrics(
            total_scenarios=self._total_scenarios,
            avg_alignment=float(avg),
            calibration_flag=self._calibration_flag,
            buffer_usage=len(self._outcome_buffer) / self._outcome_buffer.maxlen if self._outcome_buffer.maxlen else 1,
            last_alignment=self._alignment_history[-1][0] if self._alignment_history else 0.0,
        )

    async def generate_scenario(self, context: Optional[Dict] = None) -> PhantomScenario:
        """Gera cenário contrafactual."""
        scenario_id = f"scenario_{self._total_scenarios:06d}"
        return self._generator.generate(scenario_id=scenario_id, context=context or {})

    async def simulate_execution(
        self,
        scenario: PhantomScenario,
        decision: Dict[str, Any],
        real_rr: Optional[float] = None,
    ) -> PhantomOutcome:
        """
        Simula execução. Non-blocking com semaphore.
        Atualiza alignment history e calibration flag.
        """
        async with self._semaphore:
            outcome = await self._simulator.simulate_execution(scenario, decision, real_rr)

        # Store outcome (bounded ring buffer)
        self._outcome_buffer.append(outcome)
        self._total_scenarios += 1

        # Update alignment tracking
        if real_rr is not None:
            deviation = abs(outcome.rr_simulated - real_rr)
            self._update_calibration(deviation)

        self._alignment_history.append((outcome.alignment_score, time.time_ns()))
        return outcome

    async def align_with_reality(self, real_rr: float, phantom_rr: float) -> float:
        """
        RealityAnchor protocol.
        Retorna alignment score [0, 1].
        Atualiza calibration se deviation > threshold.
        """
        deviation = abs(phantom_rr - real_rr)
        alignment = float(1.0 - min(1.0, deviation))
        self._update_calibration(deviation)
        self._alignment_history.append((alignment, time.time_ns()))
        return alignment

    def _update_calibration(self, deviation: float) -> None:
        """
        Se deviation > CALIBRATION_DEVIATION incrementa counter.
        Se counter > MAX_CALIBRATION_CYCLES ativa calibration_flag.
        Se deviation < threshold, reseta counter e flag.
        """
        if deviation > CALIBRATION_DEVIATION:
            self._calibration_counter += 1
            if self._calibration_counter >= MAX_CALIBRATION_CYCLES:
                self._calibration_flag = True
        else:
            self._calibration_counter = 0
            self._calibration_flag = False

    def estimate_shadow_gradient(self, outcome: PhantomOutcome) -> Dict[str, float]:
        """Retorna gradient vector do outcome, já clipado do simulador."""
        return dict(outcome.gradient_vector)

    async def run_background_loop(
        self,
        handler: Optional[Callable[[], Coroutine]] = None,
        interval: float = 1.0,
    ) -> None:
        """
        Background loop non-blocking para geração contínua de cenários.
        CPU capped via semaphore. Para com stop().
        """
        self._running = True
        while self._running:
            try:
                if handler:
                    await asyncio.wait_for(handler(), timeout=30.0)
                else:
                    # Default: generate scenario e simular
                    scenario = await self.generate_scenario()
                    await self.simulate_execution(
                        scenario,
                        decision={"side": "long", "size": 1.0, "confidence": 0.5},
                    )
                await asyncio.sleep(interval)
            except Exception:
                # Graceful degradation: log and continue
                await asyncio.sleep(interval * 2)

    def stop(self) -> None:
        self._running = False
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()

    def get_latest_outcomes(self, n: int = 10) -> List[PhantomOutcome]:
        """Retorna últimos n outcomes."""
        return list(self._outcome_buffer)[-n:]

    def get_calibration_status(self) -> Dict[str, Any]:
        """Status detailed do calibration."""
        return {
            "calibration_flag": self._calibration_flag,
            "calibration_counter": self._calibration_counter,
            "alignment_samples": len(self._alignment_history),
            "threshold": CALIBRATION_DEVIATION,
            "max_cycles": MAX_CALIBRATION_CYCLES,
        }
