# @module: aevara.src.phantom.alignment_tracker
# @deps: aevara.src.phantom.execution_simulator
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: RealityAnchor protocol tracker. Monitora ghost-vs-real metrics,
#           calibration flags, e congela promocao de DNA quando alinhamento insuficiente.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from aevara.src.phantom.execution_simulator import PhantomOutcome


@dataclass(frozen=True, slots=True)
class AlignmentReading:
    """Leitura pontual de alinhamento."""
    timestamp_ns: int
    phantom_rr: float
    real_rr: float
    deviation: float
    alignment_score: float
    calibration_active: bool


@dataclass
class RealityAnchor:
    """
    Protocolo de ancoragem fantasma-realidade.
    Se |RR_phantom - RR_real| > 0.15 por >5 ciclos, ativa calibration_flag,
    congela promotion de DNA até recalibração.
    """

    threshold: float = 0.15
    max_consecutive_violations: int = 5
    _history: List[AlignmentReading] = field(default_factory=list)
    _consecutive_violations: int = field(default=0)
    _calibration_active: bool = field(default=False)

    def record(self, phantom_rr: float, real_rr: float, timestamp_ns: int) -> AlignmentReading:
        """Registra leitura de alinhamento. Atualiza calibration status."""
        deviation = abs(phantom_rr - real_rr)
        alignment = max(0.0, min(1.0, 1.0 - deviation))

        if deviation > self.threshold:
            self._consecutive_violations += 1
            if self._consecutive_violations >= self.max_consecutive_violations:
                self._calibration_active = True
        else:
            self._consecutive_violations = 0
            self._calibration_active = False

        reading = AlignmentReading(
            timestamp_ns=timestamp_ns,
            phantom_rr=phantom_rr,
            real_rr=real_rr,
            deviation=deviation,
            alignment_score=alignment,
            calibration_active=self._calibration_active,
        )
        self._history.append(reading)
        return reading

    @property
    def calibration_active(self) -> bool:
        return self._calibration_active

    def get_avg_alignment(self, window: int = 20) -> float:
        if not self._history:
            return 0.0
        recent = self._history[-window:]
        return sum(r.alignment_score for r in recent) / len(recent)

    def get_history(self) -> List[AlignmentReading]:
        return list(self._history)

    def is_promotion_safe(self) -> bool:
        """DNA promotion só é segura quando calibration inativa."""
        return not self._calibration_active

    def reset(self) -> None:
        self._history.clear()
        self._consecutive_violations = 0
        self._calibration_active = False
