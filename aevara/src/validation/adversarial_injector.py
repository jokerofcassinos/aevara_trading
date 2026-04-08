# @module: aevara.src.validation.adversarial_injector
# @deps: numpy, dataclasses, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Injecao adversarial controlada em dados de validacao:
#           flash crash, latency spike, spoofing wave, fat tail regime.
#           Permite comparar metricas pre/pos injecao.

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class InjectionType(str, Enum):
    FLASH_CRASH = "FLASH_CRASH"
    LATENCY_SPIKE = "LATENCY_SPIKE"
    SPOOFING_WAVE = "SPOOFING_WAVE"
    FAT_TAIL = "FAT_TAIL"
    VOLATILITY_CLUSTER = "VOLATILITY_CLUSTER"
    GAP_EVENT = "GAP_EVENT"


@dataclass(frozen=True, slots=True)
class InjectionConfig:
    """Configuracao de injecao adversarial."""
    flash_crash_sigma: float = 5.0
    flash_crash_duration: int = 3
    latency_increase_factor: float = 10.0
    spoof_cancel_rate: float = 0.80
    fat_tail_alpha: float = 2.0
    vol_multiplier: float = 3.0
    gap_sigma: float = 0.05


@dataclass(frozen=True, slots=True)
class InjectionReport:
    """Relatorio de injecao com impacto metrico."""
    injection_type: InjectionType
    n_points_affected: int
    severity: float
    pre_mean: float
    post_mean: float
    pre_std: float
    post_std: float
    return_impact_pct: float


class AdversarialInjector:
    """
    Injeta cenarios adversariais em series de retornos/precso.

    Invariantes:
    - Original NAO modificado (copia sempre)
    - Severidade parametrizavel (0-1)
    - Report pre/pos injecao obrigatorio
    - Reprodutivel via seed
    """

    def __init__(self, config: Optional[InjectionConfig] = None, seed: Optional[int] = None):
        self._config = config or InjectionConfig()
        self._rng = np.random.default_rng(seed)

    def inject_flash_crash(
        self, returns: np.ndarray, start_idx: int, severity: float = 1.0
    ) -> Tuple[np.ndarray, InjectionReport]:
        """
        Flash crash: drop abrupto seguido de recovery parcial.
        """
        result = returns.copy()
        cfg = self._config
        duration = int(cfg.flash_crash_duration * severity)
        sigma = cfg.flash_crash_sigma * severity

        base_sigma = np.std(returns) if len(returns) > 1 else 0.01
        crash_magnitude = -sigma * base_sigma

        pre_returns = returns[start_idx:start_idx + duration]

        for i in range(duration):
            idx = start_idx + i
            if idx < len(result):
                # Crash descendente com recovery parcial no final
                t = i / max(duration - 1, 1)
                crash = crash_magnitude * (1 - t * 0.5)  # Recovery 50%
                result[idx] = returns[idx] + crash

        return result, self._make_report(
            InjectionType.FLASH_CRASH,
            result, returns, start_idx, start_idx + duration, severity
        )

    def inject_volatility_cluster(
        self, returns: np.ndarray, start_idx: int, duration: int = 20,
        severity: float = 1.0
    ) -> Tuple[np.ndarray, InjectionReport]:
        """
        Cluster de volatilidade: periodo de alta vol concentrada.
        """
        result = returns.copy()
        multiplier = self._config.vol_multiplier * severity
        base_std = np.std(returns) if len(returns) > 1 else 0.01

        end_idx = min(start_idx + duration, len(result))

        for i in range(start_idx, end_idx):
            shock = self._rng.normal(0, base_std * (multiplier - 1))
            result[i] = returns[i] + shock

        return result, self._make_report(
            InjectionType.VOLATILITY_CLUSTER,
            result, returns, start_idx, end_idx, severity
        )

    def inject_gap(
        self, returns: np.ndarray, idx: int, severity: float = 1.0
    ) -> Tuple[np.ndarray, InjectionReport]:
        """
        Gap: salto unico no preco/retorno.
        """
        result = returns.copy()
        direction = self._rng.choice([-1, 1])
        gap_magnitude = direction * self._config.gap_sigma * severity

        if 0 <= idx < len(result):
            result[idx] = returns[idx] + gap_magnitude

        return result, self._make_report(
            InjectionType.GAP_EVENT,
            result, returns, idx, idx + 1, severity
        )

    def inject_fat_tail(
        self, returns: np.ndarray, fraction: float = 0.1, severity: float = 1.0
    ) -> Tuple[np.ndarray, InjectionReport]:
        """
        Substitui fracao dos retornos por amostras Pareto (cauda pesada).
        """
        result = returns.copy()
        n = len(returns)
        n_replace = max(1, int(n * fraction))
        alpha = self._config.fat_tail_alpha / severity

        indices = self._rng.choice(n, size=n_replace, replace=False)
        # Pareto com cauda pesada bilateral
        pareto_samples = self._rng.pareto(alpha, size=n_replace)
        signs = self._rng.choice([-1, 1], size=n_replace)

        for i, idx in enumerate(indices):
            result[idx] = signs[i] * pareto_samples[i] * 0.05

        return result, self._make_report(
            InjectionType.FAT_TAIL,
            result, returns, 0, n, severity
        )

    def inject_latency_spread(
        self, returns: np.ndarray, base_latency_ms: np.ndarray,
        severity: float = 1.0
    ) -> Tuple[np.ndarray, InjectionReport]:
        """
        Simula impacto de latencia: slippage proporcional a latencia.
        """
        result = returns.copy()
        factor = self._config.latency_increase_factor * severity
        latencies = base_latency_ms * factor

        # Slippage estimado: latencia * vol (simplificado)
        vol = np.std(returns) if len(returns) > 1 else 0.01
        slippage = latencies / 1000.0 * vol * 0.01  # Normalizado

        for i in range(len(result)):
            result[i] = returns[i] - abs(slippage[i])  # Slippage prejudica

        return result, self._make_report(
            InjectionType.LATENCY_SPIKE,
            result, returns, 0, len(result), severity
        )

    def _make_report(
        self,
        injection_type: InjectionType,
        modified: np.ndarray,
        original: np.ndarray,
        start: int,
        end: int,
        severity: float,
    ) -> InjectionReport:
        """Cria relatorio de impacto de injecao."""
        start = max(0, start)
        end = min(len(modified), end)
        n_affected = max(0, end - start)

        pre_mean = float(np.mean(original[start:end])) if n_affected > 0 else 0.0
        post_mean = float(np.mean(modified[start:end])) if n_affected > 0 else 0.0
        pre_std = float(np.std(original[start:end])) if n_affected > 0 else 0.0
        post_std = float(np.std(modified[start:end])) if n_affected > 0 else 0.0

        impact = abs(post_mean - pre_mean) / (abs(pre_mean) if abs(pre_mean) > 1e-10 else 1e-10)

        return InjectionReport(
            injection_type=injection_type,
            n_points_affected=n_affected,
            severity=severity,
            pre_mean=pre_mean,
            post_mean=post_mean,
            pre_std=pre_std,
            post_std=post_std,
            return_impact_pct=impact * 100,
        )

    def multi_inject(
        self,
        returns: np.ndarray,
        injections: List[Tuple[str, int, float]],
    ) -> Tuple[np.ndarray, List[InjectionReport]]:
        """
        Aplica multiplas injecoes.

        Args:
            returns: array original de retornos
            injections: lista de (type_str, start_idx, severity)

        Returns:
            (modified_returns, reports)
        """
        result = returns.copy()
        reports: List[InjectionReport] = []

        for inj_type, start_idx, severity in injections:
            if inj_type == "flash_crash":
                result, report = self.inject_flash_crash(result, start_idx, severity)
            elif inj_type == "gap":
                result, report = self.inject_gap(result, start_idx, severity)
            elif inj_type == "fat_tail":
                result, report = self.inject_fat_tail(result, severity=severity)
            elif inj_type == "vol_cluster":
                result, report = self.inject_volatility_cluster(result, start_idx, severity=severity)
            else:
                continue
            reports.append(report)

        return result, reports
