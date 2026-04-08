# @module: aevara.src.integration.latency_profiler
# @deps: time, collections
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: High-resolution async profiler tracking p50/p95/p99 per pipeline stage with overflow-safe ring buffer.

from __future__ import annotations
import time
from collections import deque
from typing import Dict, List, Optional
import statistics

class LatencyProfiler:
    """
    Perfilador assincrono de alta resolucao por estagio do pipeline.
    """
    def __init__(self, buffer_size: int = 1000):
        self._history: Dict[str, deque[int]] = {}
        self._buffer_size = buffer_size
        self._current_stages: Dict[str, int] = {}
        self._budget_us = 50000  # 50ms default p99 budget

    def start_stage(self, stage: str) -> int:
        now = time.perf_counter_ns()
        self._current_stages[stage] = now
        return now

    def end_stage(self, stage: str, start_ns: Optional[int] = None) -> int:
        end = time.perf_counter_ns()
        start = start_ns or self._current_stages.pop(stage, end)
        duration_us = (end - start) // 1000
        
        if stage not in self._history:
            self._history[stage] = deque(maxlen=self._buffer_size)
        self._history[stage].append(duration_us)
        return duration_us

    def get_percentiles(self, stage: str) -> Dict[str, int]:
        if stage not in self._history or not self._history[stage]:
            return {"p50": 0, "p95": 0, "p99": 0}
        
        data = sorted(list(self._history[stage]))
        n = len(data)
        return {
            "p50": data[int(n * 0.50)],
            "p95": data[int(n * 0.95)] if n > 20 else data[-1],
            "p99": data[int(n * 0.99)] if n > 100 else data[-1],
        }

    def get_e2e_budget_status(self) -> str:
        # Sum of P99s for all stages
        total_p99 = sum(self.get_percentiles(s)["p99"] for s in self._history)
        if total_p99 <= self._budget_us:
            return "WITHIN_BUDGET"
        if total_p99 <= self._budget_us * 1.5:
            return "WARNING"
        return "BREACH"
