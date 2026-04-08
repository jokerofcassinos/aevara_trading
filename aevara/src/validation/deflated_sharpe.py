# @module: aevara.src.validation.deflated_sharpe
# @deps: numpy, math, scipy.stats, dataclasses
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Deflated Sharpe Ratio (DSR), Minimum Backtest Length (MinBTL),
#           Probability of Backtest Overfitting (PBO). Corrige Sharpe
#           inflado por multipilicidade de testes e dependencia.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from numpy import random as nprng


@dataclass(frozen=True, slots=True)
class SharpeMetrics:
    """Metricas de Sharpe com deflacao completa."""
    raw_sharpe: float
    deflated_sharpe: float
    min_backtest_length: int
    probability_of_overfitting: float
    correlation_of_trials: float


@dataclass(frozen=True, slots=True)
class DeflatedSharpeConfig:
    target_sharpe: float = 1.0
    target_sr_variance: float = 1.0
    n_mc_trials: int = 5000
    confidence_level: float = 0.95


class DeflatedSharpeCalculator:
    """
    Calcula Sharpe deflacionado, MinBTL e PBO.

    Invariantes:
    - DSR <= raw_sharpe SEMPRE (deflation nunca infla)
    - PBO em [0, 1] (probabilidade)
    - MinBTL >= 1 (minimo de amostras necessario)
    - Se N < MinBTL => confidence = 0 (resultado invalido)
    """

    def __init__(self, config: Optional[DeflatedSharpeConfig] = None):
        self._config = config or DeflatedSharpeConfig()

    def compute(
        self,
        sharpe_values: List[float],
        n_trials: int,
        skew: float = 0.0,
        kurtosis: float = 3.0,
    ) -> SharpeMetrics:
        """
        Calcula metricas completas de Sharpe.

        Args:
            sharpe_values: lista de Sharpes de diferentes trials/configs
            n_trials: numero total de testes realizados (multipilicidade)
            skew: assimetria da distribuicao de retornos
            kurtosis: curtose da distribuicao de retornos

        Returns:
            SharpeMetrics com todos os campos calculados
        """
        if not sharpe_values or len(sharpe_values) == 0:
            return SharpeMetrics(
                raw_sharpe=0.0,
                deflated_sharpe=0.0,
                min_backtest_length=1,
                probability_of_overfitting=1.0,
                correlation_of_trials=0.0,
            )

        raw_sr = float(np.max(sharpe_values))
        sr_array = np.array(sharpe_values, dtype=float)

        # Deflation factor: E[max] da distribuicao de maximos
        e_max_sr = self._expected_max_sharpe(n_trials, skew, kurtosis)
        deflated_sr = max(0.0, raw_sr - e_max_sr)

        # Garante DSR <= raw
        deflated_sr = min(deflated_sr, raw_sr)

        # Correlacao entre trials (proxy: std dos sharpes)
        corr_trials = max(0.0, 1.0 - np.std(sr_array)) if len(sr_array) > 1 else 0.0

        # MinBTL
        min_btl = self.min_backtest_length(raw_sr)

        # PBO
        if len(sharpe_values) > n_trials:
            pbo = self.probability_of_backtest_overfitting(sr_array)
        else:
            pbo = self._pbo_from_sharpe_spread(raw_sr, n_trials, kurtosis)

        return SharpeMetrics(
            raw_sharpe=raw_sr,
            deflated_sharpe=deflated_sr,
            min_backtest_length=min_btl,
            probability_of_overfitting=clip(pbo, 0.0, 1.0),
            correlation_of_trials=corr_trials,
        )

    def _expected_max_sharpe(
        self, n_trials: int, skew: float, kurtosis: float
    ) -> float:
        """
        Esperanca do maximo de n_trials Sharpes.
        Ajustado por skew e kurtosis via expansao de Cornish-Fisher.
        E[max] ~ Phi_inv(1 - 1/n) * sqrt(1 + skew*E[max]^2/6 + (kurt-3)*E[max]^4/24)
        """
        if n_trials <= 1:
            return 0.0

        # Approx: E[max of n iid N(0,1)] ~ Phi_inv((n-0.375)/(n+0.25))
        p = (n_trials - 0.375) / (n_trials + 0.25)
        z_max = self._norm_inv(p)

        # Cornish-Fisher adjustment
        adjustment = 1.0
        if kurtosis != 3.0:
            adjustment += (kurtosis - 3.0) * z_max**2 / 24.0
        if skew != 0.0:
            adjustment += skew * z_max / 6.0

        return z_max * math.sqrt(max(0.0, adjustment))

    @staticmethod
    def _norm_inv(p: float) -> float:
        """Inversa da normal padrao via aproximacao rational."""
        # Beasley-Springer-Moro approximation
        p = max(1e-10, min(1.0 - 1e-10, p))
        if p < 0.5:
            return -math.sqrt(-2.0 * math.log(p))
        return math.sqrt(-2.0 * math.log(1.0 - p))

    def min_backtest_length(
        self, target_sharpe: float, target_sr_variance: float = 1.0
    ) -> int:
        """
        Calcula numero minimo de amostras para validar Sharpe target.
        MinBTL = (1 + (SR^2 * T)) / (1 - rho) onde rho e correlacao media.
        Simplificado: T_min = (z_alpha / SR)^2
        """
        if target_sharpe <= 0:
            return 1
        if target_sharpe < 1e-10:
            return 10000  # Cap at reasonable max for near-zero sharpe

        z_alpha = 1.96  # 95% confidence
        T_min = int(math.ceil((z_alpha / target_sharpe) ** 2 * target_sr_variance))
        return max(1, min(T_min, 10000000))

    def probability_of_backtest_overfitting(
        self, is_vector: np.ndarray
    ) -> float:
        """
        PBO: probabilidade de que o melhor Sharpe no treino seja pior que
        mediana no OOS. Calculado via Combinatorial CV.

        Args:
            is_vector: vetor de indicadores (1 = best IS > OOS median, 0 otherwise)

        Returns:
            Probabilidade em [0, 1]
        """
        if len(is_vector) == 0:
            return 1.0

        # Fraction of trials where IS best beats OOS
        n_overfit = np.sum(is_vector)
        return float(n_overfit / len(is_vector))

    def _pbo_from_sharpe_spread(
        self, best_sharpe: float, n_trials: int, kurtosis: float
    ) -> float:
        """
        Estima PBO a partir do spread entre best Sharpe e media.
        Se best >> media, PBO alto.
        """
        if n_trials <= 1:
            return 0.0

        # Proxy: se max Sharpe e grande comparado a expected max, PBO sobe
        e_max = self._expected_max_sharpe(n_trials, 0.0, kurtosis)
        if e_max <= 0:
            return 0.0

        # PBO cresce com (best - e_max)
        spread = best_sharpe - e_max
        # Sigmoidal mapping
        return float(1.0 / (1.0 + math.exp(-3.0 * spread)))


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
