# @module: aevara.src.strategy.parameter_sweeper
# @deps: typing, asyncio, random, numpy
# @status: IMPLEMENTED_STRATEGIC_v1.0
# @last_update: 2026-04-10
# @summary: Async-safe online parameter optimizer using adaptive stochastic search.

from __future__ import annotations
import asyncio
import random
import numpy as np
import time
from typing import Any, Dict, List, Optional, Callable
from aevara.src.telemetry.structured_logger import logger

class ParameterSweeper:
    """
    Varredor de Parâmetros (Ω-15).
    Otimizador online assíncrono para ajuste de parâmetros de estratégia em runtime.
    """
    def __init__(self, budget: int = 20):
        self.budget = budget
        self._is_running = False

    async def online_optimize(self, objective_fn: Callable, param_bounds: Dict[str, tuple], timeout: float = 30.0) -> Dict[str, float]:
        """
        Executa otimização estocástica adaptativa em um thread pool para não bloquear o loop.
        """
        if self._is_running:
            return {}

        self._is_running = True
        start_time = time.time()
        
        try:
            # Rodar em thread para cálculos intensivos (pseudo-Bayesian/Stochastic search)
            best_params = await asyncio.to_thread(self._stochastic_search, objective_fn, param_bounds, timeout)
            
            logger.log("META", f"Parameter Sweeper: Optimization complete in {time.time() - start_time:.2f}s")
            return best_params
        except Exception as e:
            logger.log("ERROR", f"Parameter Sweeper Error: {e}")
            return {}
        finally:
            self._is_running = False

    def _stochastic_search(self, objective_fn: Callable, param_bounds: Dict[str, tuple], timeout: float) -> Dict[str, float]:
        """Busca estocástica adaptativa (Hill Climbing + Random Restarts)."""
        best_score = -float('inf')
        best_params = {k: random.uniform(v[0], v[1]) for k, v in param_bounds.items()}
        
        start_time = time.time()
        
        for i in range(self.budget):
            if time.time() - start_time > timeout:
                break
                
            # Candidate generation (Mutation from current best)
            candidate = {}
            for k, (low, high) in param_bounds.items():
                scale = (high - low) * 0.1 # 10% mutation range
                candidate[k] = np.clip(best_params[k] + random.gauss(0, scale), low, high)
            
            # Evaluate (Simulated or Backtest-based)
            score = objective_fn(candidate)
            
            if score > best_score:
                best_score = score
                best_params = candidate
                
        return best_params
