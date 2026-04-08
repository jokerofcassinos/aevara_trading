# @module: aevara.src.portfolio.multi_strategy_allocator
# @deps: numpy, scipy.stats, dataclasses, typing, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Bayesian Thompson Sampling allocator with regime-adjusted posteriors and bounded portfolio weights.

from __future__ import annotations
import numpy as np
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from scipy import stats

@dataclass(frozen=True, slots=True)
class AllocationState:
    """Estado atômico da alocação de portfólio."""
    strategy_weights: Dict[str, float]  # Σ = 1.0
    posterior_params: Dict[str, Tuple[float, float]]  # Beta(α, β) per strategy
    regime_weights: Dict[str, Dict[str, float]]  # regime -> {strat: weight}
    last_rebalance_ns: int
    drift_pct: float

class MultiStrategyAllocator:
    """
    Alocador Bayesian Thompson Sampling (v1.0).
    Atualiza posteriors Beta(α, β) por trade realizado e otimiza alocação
    com base em Thompson Sampling para resolver o trade-off exploração/explotação.
    """
    def __init__(self, strategies: List[str], prior_alpha: float = 1.0, prior_beta: float = 1.0):
        self._strategies = strategies
        # priors p(performance) ~ Beta(α, β)
        self._posteriors: Dict[str, List[float]] = {s: [prior_alpha, prior_beta] for s in strategies}
        self._regime_decay = 0.85 # λ decay para transição de regime
        self._last_rebalance = time.time_ns()

    def sample_weights(self) -> Dict[str, float]:
        """
        Realiza Thompson Sampling das posteriors e normaliza pesos.
        Cada amostragem representa uma 'tese' de performance futura.
        """
        samples = {}
        for s in self._strategies:
             alpha, beta = self._posteriors[s]
             samples[s] = np.random.beta(alpha, beta)
        
        total = sum(samples.values()) or 1.0
        return {s: (val / total) for s, val in samples.items()}

    def update_posterior(self, strategy: str, realized_return: float, regime_change: bool = False) -> None:
        """
        Atualiza parâmetros da posterior com base no retorno realizado (Bernoulli update).
        Se houver mudança de regime, aplica decaimento (λ) para esquecimento controlado.
        """
        if regime_change:
             # Esquecimento anti-entrópico de regimes passados
             for s in self._strategies:
                  self._posteriors[s][0] = self._posteriors[s][0] * self._regime_decay + 1.0
                  self._posteriors[s][1] = self._posteriors[s][1] * self._regime_decay + 1.0
        
        # Bayesian Update: if ret > 0 (suceso α+1), if ret < 0 (falha β+1)
        if realized_return > 0:
             self._posteriors[strategy][0] += 1.0
        else:
             self._posteriors[strategy][1] += 1.0

    def allocate_with_constraints(self, raw_weights: Dict[str, float], max_correlation: float = 0.6, corr_matrix: Optional[np.ndarray] = None) -> Dict[str, float]:
        """
        Aplica penalização de correlação (ρ) nos pesos crus.
        Se ativos estão muito correlacionados, reduz exposição proporcionalmente.
        """
        # Implementação simplificada de Risk-Parity/Constraint
        if corr_matrix is None: return raw_weights
        
        # Penaliza ativos com alta correlação média no portfólio
        mean_corr = np.mean(corr_matrix, axis=0)
        adjusted_weights = {}
        for i, s in enumerate(self._strategies):
             penalty = 1.0 if mean_corr[i] <= max_correlation else max(0.1, 1.0 - (mean_corr[i] - max_correlation))
             adjusted_weights[s] = raw_weights[s] * penalty
        
        total = sum(adjusted_weights.values()) or 1.0
        return {s: (v / total) for s, v in adjusted_weights.items()}

    def get_current_allocation(self) -> AllocationState:
        weights = self.sample_weights() # Realiza amostragem atual
        return AllocationState(
            strategy_weights=weights,
            posterior_params={s: (p[0], p[1]) for s, p in self._posteriors.items()},
            regime_weights={}, # Placeholder for regime mapping
            last_rebalance_ns=self._last_rebalance,
            drift_pct=0.0
        )
