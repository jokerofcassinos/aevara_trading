# @module: aevara.src.validation.walk_forward
# @deps: numpy, dataclasses, typing, math, time
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Walk-forward analysis com regime stratification, rolling OOS,
#           adaptive window sizing e tracking de performance por regime.
#           Nao mistura regimes na mesma validacao.

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Awaitable
from concurrent.futures import ThreadPoolExecutor

import numpy as np


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    """Split de walk-forward: janela rolling com treino e OOS isolados."""
    train_start: int
    train_end: int
    oos_start: int
    oos_end: int
    regime: str
    step: int


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """Resultado agregado de walk-forward analysis."""
    total_steps: int
    mean_oos_return: float
    std_oos_return: float
    oos_sharpe: float
    regime_results: Dict[str, Dict[str, float]]
    max_drawdown: float
    win_rate: float
    n_per_regime: Dict[str, int]


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    initial_train_size: int = 200
    step_size: int = 20
    oos_size: int = 50
    min_oos_samples: int = 10
    max_steps: int = 100


class WalkForwardEngine:
    """
    Walk-forward analysis com regime stratification.

    Invariantes:
    - Janela de treino NAO sobrepoem com OOS
    - Regime tag por step: performance agregada por regime
    - Adaptive sizing: se dados insuficientes, para
    - OOS isolado: nenhum dado do OOS usado no treino
    - Drawdown tracking: running peak to trough
    """

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self._config = config or WalkForwardConfig()

    def generate_splits(
        self,
        timestamps: np.ndarray,
        regimes: np.ndarray,
        max_steps: int = 0,
    ) -> List[WalkForwardSplit]:
        """
        Gera splits rolling de walk-forward.

        Args:
            timestamps: array ordenado de timestamps
            regimes: array de regime labels
            max_steps: limite de steps (0 = usa config)

        Returns:
            Lista ordenada de WalkForwardSplit
        """
        assert len(timestamps) == len(regimes)
        n = len(timestamps)
        cfg = self._config
        steps_limit = max_steps if max_steps > 0 else cfg.max_steps

        train_start = 0
        train_end = cfg.initial_train_size

        if train_end >= n - cfg.oos_size:
            return []

        splits: List[WalkForwardSplit] = []
        for step in range(steps_limit):
            oos_start = train_end
            oos_end = min(oos_start + cfg.oos_size, n)

            if oos_end - oos_start < cfg.min_oos_samples:
                break
            if oos_end > n:
                break

            # Regime dominante no OOS
            oos_regimes = regimes[oos_start:oos_end]
            regime = str(np.unique(oos_regimes, return_counts=True)[0][
                np.argmax(np.unique(oos_regimes, return_counts=True)[1])
            ])

            splits.append(WalkForwardSplit(
                train_start=train_start,
                train_end=train_end,
                oos_start=oos_start,
                oos_end=oos_end,
                regime=regime,
                step=step,
            ))

            # Slide window
            train_start += cfg.oos_size
            train_end = train_start + cfg.initial_train_size
            if train_end > n:
                train_end = n

            if train_end - train_start < cfg.min_oos_samples:
                break

        return splits

    def verify_no_leakage(self, splits: List[WalkForwardSplit]) -> bool:
        """Verifica que nenhum indice OOS sobrepoem com train."""
        for split in splits:
            if split.oos_start < split.train_end:
                return False
        return True

    def generate_regime_stratified(
        self, timestamps: np.ndarray, regimes: np.ndarray
    ) -> Dict[str, List[WalkForwardSplit]]:
        """
        Gera walk-forward separado por regime.
        Cada regime tem splits independentes.
        """
        unique_regimes = np.unique(regimes)
        result: Dict[str, List[WalkForwardSplit]] = {}

        for regime in unique_regimes:
            regime_mask = regimes == regime
            indices = np.where(regime_mask)[0]

            if len(indices) < self._config.initial_train_size + self._config.min_oos_samples:
                continue

            regime_timestamps = timestamps[indices]
            regime_regimes = regimes[indices]

            splits = self.generate_splits(regime_timestamps, regime_regimes)
            if splits:
                result[str(regime)] = splits

        return result

    def evaluate(
        self,
        returns: np.ndarray,
        splits: List[WalkForwardSplit],
    ) -> WalkForwardResult:
        """
        Avalia performance nos splits OOS.

        Args:
            returns: array de retornos
            splits: lista de splits de walk-forward

        Returns:
            WalkForwardResult com metricas agregadas
        """
        if not splits or len(returns) == 0:
            return WalkForwardResult(
                total_steps=0,
                mean_oos_return=0.0,
                std_oos_return=0.0,
                oos_sharpe=0.0,
                regime_results={},
                max_drawdown=0.0,
                win_rate=0.0,
                n_per_regime={},
            )

        oos_returns: List[float] = []
        regime_returns: Dict[str, List[float]] = {}
        cumulative = 1.0
        peak = cumulative
        max_dd = 0.0

        for split in splits:
            oos_rets = returns[split.oos_start:split.oos_end]
            if len(oos_rets) == 0:
                continue

            for ret in oos_rets:
                oos_returns.append(float(ret))
                cumulative *= (1 + ret)
                peak = max(peak, cumulative)
                drawdown = (peak - cumulative) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, drawdown)

                if split.regime not in regime_returns:
                    regime_returns[split.regime] = []
                regime_returns[split.regime].append(float(ret))

        oos_array = np.array(oos_returns)
        mean_ret = float(np.mean(oos_array)) if len(oos_array) > 0 else 0.0
        std_ret = float(np.std(oos_array)) if len(oos_array) > 1 else 0.0
        sharpe = mean_ret / std_ret if std_ret > 0 else 0.0
        win_rate = float(np.mean(oos_array > 0)) if len(oos_array) > 0 else 0.0

        # Resultados por regime
        regime_results: Dict[str, Dict[str, float]] = {}
        n_per_regime: Dict[str, int] = {}
        for regime, rets in regime_returns.items():
            rets_np = np.array(rets)
            regime_results[regime] = {
                "mean": float(np.mean(rets_np)),
                "std": float(np.std(rets_np)),
                "sharpe": float(np.mean(rets_np) / np.std(rets_np)) if np.std(rets_np) > 0 else 0.0,
                "count": len(rets_np),
            }
            n_per_regime[regime] = len(rets_np)

        return WalkForwardResult(
            total_steps=len(splits),
            mean_oos_return=mean_ret,
            std_oos_return=std_ret,
            oos_sharpe=sharpe,
            regime_results=regime_results,
            max_drawdown=max_dd,
            win_rate=win_rate,
            n_per_regime=n_per_regime,
        )
