# @module: aevara.src.portfolio.sizing_telemetry
# @deps: typing, time, dataclasses, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Telemetry dedicated to sizing: f_allocado, f_theorico, constraint_penalties, ergodic_growth_rate.

from __future__ import annotations
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from aevara.src.portfolio.stochastic_sizer import SizingResult

class SizingTelemetry:
    """
    Painel de Telemetria de Sizing (v1.0.0).
    Rastreia a decomposição de penalidades e a taxa de crescimento ergódico global.
    Permite diagnosticar se as restrições FTMO estão podando o alpha (Ω-45).
    """
    def __init__(self):
        self._log: List[SizingResult] = []
        self._max_len = 100

    def record(self, result: SizingResult):
        """Registra e emite métricas via TelemetryMatrix."""
        self._log.append(result)
        if len(self._log) > self._max_len:
             self._log.pop(0)
             
        # Log-odds fusion analysis (proxy)
        penalty_total = sum(result.applied_penalties.values())
        drag = (penalty_total / (result.theoretical_fraction or 1.0)) * 100.0
        
        # Output Metrics (Stdout fallback, logic placeholder for MetricsStream)
        print(f"AEVRA TELEMETRY SIZING [{result.symbol}]: "
              f"Theory: {result.theoretical_fraction*100:.2f}% | "
              f"Final: {result.allocated_fraction*100:.2f}% | "
              f"Constraint Drag: {drag:.1f}% | "
              f"Growth: {result.ergodic_growth_contribution*1e4:.2f} bps")

    def get_avg_drag(self) -> float:
        """Calcula a média de arraste de conformidade (Compliance Drag) over 100 trades."""
        if not self._log: return 0.0
        drags = []
        for r in self._log:
             penalty = sum(r.applied_penalties.values())
             drags.append(penalty / (r.theoretical_fraction or 1.0))
        return float(np.mean(drags))
