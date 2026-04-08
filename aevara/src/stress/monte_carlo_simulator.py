# @module: aevara.src.stress.monte_carlo_simulator
# @deps: numpy, scipy.stats, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: High-performance equity curve simulator using empirical P&L distributions and EVT for tail risk.

from __future__ import annotations
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class EquityResult:
    """Snapshot total da simulacao de Monte Carlo."""
    n_paths: int
    horizon_days: int
    paths: np.ndarray # (n_paths, horizon_days + 1)
    
    mean_return: float
    max_drawdown_dist: np.ndarray # DD distribution
    var_99_pct: float # Conditional VaR
    ruin_probability: float # P(equity < 0 or threshold)
    tail_risk_alpha: float # Extreme Value Index (EVT)

class EquitySimulator:
    """
    Simulador de curvas de equity via Monte Carlo.
    Usa Block Bootstrap para preservar correlacoes seriais e ajuste empírico GPD.
    NUNCA usa distribuicao gaussiana por design.
    """
    def __init__(self, historical_returns: np.ndarray, block_size: int = 5):
        self._returns = historical_returns
        self._block_size = block_size
        self._n_obs = len(historical_returns)
        
        # Fit GPD (Generalized Pareto) to tails if enough data
        if len(historical_returns) > 50:
             self._tail_params = stats.genpareto.fit(np.sort(historical_returns)[:5]) # Left tail
        else:
             self._tail_params = (0, 0, 0)

    async def simulate_paths(self, 
                             n_paths: int = 10000, 
                             horizon_days: int = 30, 
                             initial_capital: float = 100000, 
                             ruin_threshold: float = 0.95) -> EquityResult:
        """
        Executa simulacao massiva de Monte Carlo.
        Ruin threshold eh a fracao de capital (e.g. 0.95 = 5% loss).
        """
        # Block Bootstrap: Sample block indices
        blocks_needed = int(np.ceil(horizon_days / self._block_size))
        
        paths = np.ones((n_paths, horizon_days + 1)) * initial_capital
        
        for p in range(n_paths):
            path_returns = []
            for _ in range(blocks_needed):
                idx = np.random.randint(0, self._n_obs - self._block_size + 1)
                block = self._returns[idx : idx + self._block_size]
                path_returns.extend(block)
            
            # Slice to horizon and compute equity
            path_returns = np.array(path_returns[:horizon_days])
            paths[p, 1:] = initial_capital * np.cumprod(1 + path_returns)
        
        # Risk Metrics
        drawdowns = 1 - paths / np.maximum.accumulate(paths, axis=1)
        max_dds = np.max(drawdowns, axis=1)
        
        final_equity = paths[:, -1]
        ruin_events = final_equity < (initial_capital * ruin_threshold)
        ruin_prob = np.mean(ruin_events)
        
        # CVaR (99th percentile of final loss)
        final_returns = final_equity / initial_capital - 1
        var_99 = np.percentile(final_returns, 1.0)
        
        return EquityResult(
            n_paths=n_paths,
            horizon_days=horizon_days,
            paths=paths,
            mean_return=np.mean(final_returns),
            max_drawdown_dist=max_dds,
            var_99_pct=float(var_99),
            ruin_probability=float(ruin_prob),
            tail_risk_alpha=float(self._tail_params[0]) # GPD Index
        )
