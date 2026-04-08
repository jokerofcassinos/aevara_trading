# @module: aevara.src.telemetry.brier_calibrator
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Rolling Brier score calibration, KL divergence tracking, e
#           confidence correction via Platt scaling approximation.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np


@dataclass(frozen=True, slots=True)
class CalibrationState:
    brier_score: float
    brier_rolling: List[float]
    kl_divergence: float
    calibration_flag: bool
    sample_count: int
    correction_factor: float  # Applied to predicted confidence


class BrierCalibrator:
    """
    Calibracao de confianca via Brier score rolling.

    Invariantes:
    - Brier = 1/N * Sigma(f_i - o_i)^2, f=forecast, o=outcome (0/1)
    - Se Brier > 0.15, ativa calibration_flag
    - Rolling window fixed (max 500)
    - correction_factor bounded em [0.5, 1.5]
    """

    def __init__(
        self,
        max_window: int = 500,
        brier_threshold: float = 0.15,
    ):
        self._brier_threshold = brier_threshold
        self._forecasts: Deque[float] = deque(maxlen=max_window)
        self._outcomes: Deque[float] = deque(maxlen=max_window)
        self._brier_rolling: deque[float] = deque(maxlen=max_window)

    @property
    def sample_count(self) -> int:
        return len(self._forecasts)

    def update(self, predicted_confidence: float, actual_outcome: bool) -> None:
        """
        Registra previsao e outcome para Brier score rolling.

        Args:
            predicted_confidence: Confianca prevista [0, 1]
            actual_outcome: True se acertou a decisao
        """
        p = max(0.0, min(1.0, predicted_confidence))
        o = 1.0 if actual_outcome else 0.0

        self._forecasts.append(p)
        self._outcomes.append(o)

        # Incremental Brier
        brier = (p - o) ** 2
        self._brier_rolling.append(brier)

    def get_brier_score(self) -> float:
        if not self._brier_rolling:
            return 0.0
        return float(np.mean(list(self._brier_rolling)))

    def get_calibration_state(self) -> CalibrationState:
        """Estado completo de calibracao."""
        brier = self.get_brier_score()

        # KL divergence approximation (forecast distribution vs outcomes)
        kl = self._compute_kl_divergence()

        # Correction factor: if Brier is high, reduce confidence
        correction = 1.0
        if brier > self._brier_threshold:
            correction = max(0.5, 1.0 - brier)
        else:
            correction = min(1.5, 1.0 + (self._brier_threshold - brier) * 0.5)

        return CalibrationState(
            brier_score=brier,
            brier_rolling=list(self._brier_rolling)[-10:],  # Last 10 for display
            kl_divergence=kl,
            calibration_flag=brier > self._brier_threshold,
            sample_count=self.sample_count,
            correction_factor=correction,
        )

    def calibrate_confidence(self, raw_confidence: float) -> float:
        """Aplica correcao de calibracao a confianca bruta."""
        state = self.get_calibration_state()
        calibrated = raw_confidence * state.correction_factor
        return float(max(0.0, min(1.0, calibrated)))

    def _compute_kl_divergence(self) -> float:
        """
        KL divergence approximation: comparacao entre distribuicao
        de previsoes e distribuicao de outcomes empiricos.
        """
        if len(self._forecasts) < 10:
            return 0.0

        # Bin into 5 bins
        bins = np.linspace(0, 1, 6)
        forecast_dist, _ = np.histogram(list(self._forecasts), bins=bins)
        outcome_dist, _ = np.histogram(list(self._outcomes), bins=bins)

        # Add smoothing to avoid log(0)
        eps = 1e-7
        forecast_p = (forecast_dist + eps) / (forecast_dist.sum() + eps * len(bins))
        outcome_q = (outcome_dist + eps) / (outcome_dist.sum() + eps * len(bins))

        kl = float(np.sum(outcome_q * np.log(outcome_q / forecast_p)))
        return max(0.0, kl)

    def reset(self) -> None:
        self._forecasts.clear()
        self._outcomes.clear()
        self._brier_rolling.clear()
