# @module: aevara.src.frontier.ergodicity
# @deps: typing, numpy, dataclasses
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Ergodicity constraints engine for path-dependent survival (Ω-42). Growth rate optimization.

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass(frozen=True, slots=True)
class ErgodicityMetrics:
    path_volatility: float
    average_growth: float

class ErgodicityEngine:
    """
    Motor de Ergodicidade (Ω-42).
    Garante a sobrevivência do organismo otimizando para a média geométrica de crescimento.
    """
    def __init__(self, risk_free: float = 0.0):
        self.risk_free = risk_free

    def calculate_growth_rate(self, returns: np.ndarray) -> float:
        """
        Calcula a taxa de crescimento ergódica g = E[log(1 + r)].
        Representa o crescimento real de um sistema dependente do caminho.
        """
        if len(returns) == 0: return 0.0
        # g = mean(log(1 + r))
        # Lidamos com perdas de 100% (r = -1) via clipping para evitar log(0)
        safe_returns = np.clip(returns, -0.99, None)
        g = np.mean(np.log(1.0 + safe_returns)) - self.risk_free
        return float(g)

    def optimal_fraction(self, edge: float, variance: float, max_dd: float, dd_limit: float = 0.20) -> float:
        """
        Calcula a fração ótima (Kelly fracionário) ajustada pelo limite de drawdown path-dependent.
        f* = (edge / variance) * (1 - current_dd / limit)
        """
        if variance <= 0: return 0.001
        
        # Kelly Base
        base_f = edge / variance
        
        # Ajuste por Drawdown (Proteção Ergódica)
        dd_factor = max(0.0, 1.0 - (max_dd / dd_limit))
        f_star = base_f * dd_factor * 0.25 # Coeficiente de prudência institucional
        
        # Bounds institucionais [0.1%, 5%]
        return float(np.clip(f_star, 0.001, 0.05))

    async def apply_constraint(self, proposed_lot: float, metrics: ErgodicityMetrics) -> float:
        """Contrato de integração para o loop de decisão."""
        # TODO: Integrar com balance real para converter fração em lotes
        return proposed_lot
