# @module: aevara.src.deployment.telemetry_activation_feed
# @deps: typing, time, dataclasses, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Telemetry stream dedicated to activation dashboard: phase status, latency, drift, FTMO buffers, stability score.

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class ActivationTelemetry:
    """Métricas de telemetria de ativação (v1.0.0)."""
    phase: str
    is_halted: bool
    latency_p99: float
    reconciliation_drift: float
    ftmo_daily_buffer: float   # [0,1]
    ftmo_total_buffer: float   # [0,1]
    pilot_stability: float     # [0,1]
    timestamp_ns: int = field(default_factory=time.time_ns)

class TelemetryActivationFeed:
    """
    Painel de Ativação em Tempo Real (v1.0.0).
    Roteia o streaming de telemetria das fases críticas para o dashboard geral.
    Permite monitoramento simultâneo do CEO durante o deploy Demo/Micro.
    """
    def __init__(self):
        self._history: List[ActivationTelemetry] = []
        self._maxlen = 500

    def push(self, telemetry: ActivationTelemetry):
        """Streaming de métrica para registro e monitoramento."""
        self._history.append(telemetry)
        if len(self._history) > self._maxlen:
             self._history.pop(0)
             
        # Placeholder para routing via Dashboard (MetricsStream)
        # metrics_stream.send(telemetry)
        print(f"AEVRA TELEMETRY ACTIVATION [{telemetry.phase}]: "
              f"Latency: {telemetry.latency_p99:.2f}ms | "
              f"Drift: {telemetry.reconciliation_drift*100:.3f}% | "
              f"FTMO_B: {telemetry.ftmo_daily_buffer*100:.1f}% | "
              f"Stability: {telemetry.pilot_stability*100:.1f}%")

    def get_latest(self) -> Optional[ActivationTelemetry]:
        return self._history[-1] if self._history else None
