# @module: aevara.src.portfolio.portfolio_optimizer
# @deps: numpy, scipy.optimize, asyncio, typing, dataclasses
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Ergodic growth maximizer solving constrained optimization for multi-asset allocation (BTC/ETH/SOL).

from __future__ import annotations
import asyncio
import numpy as np
from scipy.optimize import minimize
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from aevara.src.portfolio.stochastic_sizer import SizingContext

class PortfolioOptimizer:
    """
    Otimizador Ergódico de Portfólio (v1.0.0).
    Resolve a alocação ótima multi-ativo maximizando g = E[ln(1 + fR)]. 
    Utiliza L-BFGS-B com restrições imutáveis de caixa e teto por ativo.
    """
    def __init__(self, max_iterations: int = 50, timeout_s: float = 2.0):
        self._max_iter = max_iterations
        self._timeout_s = timeout_s

    async def optimize(self, 
                       assets: List[SizingContext], 
                       constraints: Dict[str, Any]) -> Dict[str, float]:
        """
        Executa a otimização de forma assíncrona para zero-blocking.
        Frequência decision -> dispatch < 15ms (p99).
        """
        try:
             # Executa solver em thread separada (CPU bound)
             weights = await asyncio.wait_for(
                  asyncio.to_thread(self._run_solver, assets, constraints),
                  timeout=self._timeout_s
             )
             return weights
        except (asyncio.TimeoutError, Exception) as e:
             print(f"AEVRA OPTIMIZER: Solver failed or timed out ({e}). Falling back.")
             return await self.fallback_safe_allocation(assets)

    def _run_solver(self, assets: List[SizingContext], constraints: Dict) -> Dict[str, float]:
        """Inner solver loop (CPU Bound)."""
        n = len(assets)
        if n == 0: return {}
        
        # Initial guess: uniform
        x0 = np.ones(n) * (0.05 / n)
        bounds = [(0.001, 0.05) for _ in range(n)] # 5% max per asset
        
        res = minimize(
            self._objective_function,
            x0,
            args=(assets,),
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': self._max_iter}
        )
        
        if not res.success:
             return {a.symbol: 0.005 for a in assets} # Safe fallback
        
        return {a.symbol: float(w) for a, w in zip(assets, res.x)}

    def _objective_function(self, weights: np.ndarray, assets: List[SizingContext]) -> float:
        """
        Maximiza a expectativa de crescimento logarítmico (Ω-41).
        L_g = Σ_i w_i · edge_i - 0.5 * Σ_i Σ_j w_i w_j σ_i σ_j ρ_ij
        Aqui simplificado para minimizar o negativo do crescimento ergódico.
        """
        growth = 0.0
        for i, (w, a) in enumerate(zip(weights, assets)):
             # g ≈ E[r] - 0.5 * Var(r)
             # Simplificamos para Penalização Bayesiana
             item_g = w * a.edge_estimate * a.edge_confidence
             penalty = 0.5 * (w**2) * 1.5 # Volatility penalty factor (proxy)
             growth += (item_g - penalty)
        
        return -growth # SciPy minimize neg growth

    async def fallback_safe_allocation(self, assets: List[SizingContext]) -> Dict[str, float]:
        """Alocação conservadora ultra-segura para estados de pânico ou erro do solver."""
        print("AEVRA OPTIMIZER: Triggering Fallback Safe Allocation.")
        return {a.symbol: 0.002 for a in assets} # 0.2% per asset
