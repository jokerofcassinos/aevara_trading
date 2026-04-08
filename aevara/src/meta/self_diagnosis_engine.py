# @module: aevara.src.meta.self_diagnosis_engine
# @deps: typing, time, dataclasses, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Continuous health monitoring of system (Sharpe rolling, hit rate, edge decay) + degradation detection + auto-healing proposal.

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

class SelfDiagnosisEngine:
    """
    Sistema Imunológico Cognitivo (v1.0).
    Monitora métricas de saúde sistêmica (Sharpe Rolling 50 trades, Hit Rate e Edge Decay).
    Se detectar degradação p-valor ou Sharpe < 1.0, sugere 'Auto-Healing' e Emergency Reset.
    """
    def __init__(self, 
                 sharpe_min: float = 1.0, 
                 hit_rate_min: float = 0.52):
        self._sharpe_min = sharpe_min
        self._hit_rate_min = hit_rate_min
        self._last_diagnosis_ns = time.time_ns()
        self._is_healthy = True
        self._alerts: List[str] = []

    def diagnose(self, sharpe_rolling: float, hit_rate_rolling: float, edge_decay: float) -> Tuple[bool, List[str]]:
        """Executa diagnóstico global de saúde (v1.0)."""
        self._alerts = []
        
        # 1. Sharpe Check
        if sharpe_rolling < self._sharpe_min:
             self._alerts.append(f"SHARPE_DEGRADATION: {sharpe_rolling:.2f} < {self._sharpe_min}")
             self._is_healthy = False
        
        # 2. Hit Rate Check
        if hit_rate_rolling < self._hit_rate_min:
             self._alerts.append(f"HIT_RATE_DRAIN: {hit_rate_rolling*100:.1f}% < {self._hit_rate_min*100:.1f}%")
             self._is_healthy = False
             
        # 3. Edge Decay Check
        if edge_decay > 0.05: # > 5% loss of performance per analysis window
             self._alerts.append(f"EDGE_DECAY_DETECTION: Decay {edge_decay*100:.1f}% detected.")
             self._is_healthy = False

        self._last_diagnosis_ns = time.time_ns()
        return self._is_healthy, self._alerts

    def propose_auto_healing(self) -> Dict:
        """Sugere ações automáticas de cura bazeadas nos alertas."""
        if self._is_healthy: return {"action": "STAY_COURSE"}
        
        # Ações de Cura
        if "SHARPE_DEGRADATION" in str(self._alerts):
             return {"action": "RECALIBRATE_VOL_TARGET", "delta": -0.2}
        
        return {"action": "INCREASE_THRESHOLD_BUFFER", "delta": +0.1}

    def get_health_status(self) -> str:
        return "HEALTHY" if self._is_healthy else "DEGRADED"
