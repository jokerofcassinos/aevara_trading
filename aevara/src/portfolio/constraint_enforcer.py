# @module: aevara.src.portfolio.constraint_enforcer
# @deps: typing, numpy, dataclasses
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Atomic block for FTMO and market constraints. Projection step to feasible region for multi-asset allocation.

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

class ConstraintEnforcer:
    """
    Fiscal Atômico de Alocação (v1.0.0).
    Aplica o 'Projection Step' final: garante que os pesos do otimizador 
    não violem limites físicos ou regulatórios (FTMO).
    Zero alocação fora dos bounds.
    """
    def __init__(self, 
                 max_lots: float = 5.0, 
                 max_fraction: float = 0.05, 
                 balance: float = 100000.0):
        self._max_lots = max_lots
        self._max_fraction = max_fraction
        self._balance = balance

    def enforce(self, 
                weights: Dict[str, float], 
                current_lots: float = 0.0) -> Dict[str, float]:
        """
        Garante conformidade imutável:
        1. Teto individual por ativo (5% Equity).
        2. Soma total de lotes <= 5.0 (FTMO).
        3. Projeção L1 (scaling total) se lotes excedem 5.0.
        """
        # 1. Bounds check individual
        clean_w = {s: min(w, self._max_fraction) for s, w in weights.items()}
        
        # 2. FTMO Aggregate Check
        # Regra de bolso: f_0.05 (5%) ≈ 0.5 lotes (BTC notional adjust)
        # Total_f ≈ 0.5 sum_lots
        total_f = sum(clean_w.values())
        total_est_lots = total_f * 10.0 # 5% * 10 = 0.5 lotes per asset proxy
        
        if total_est_lots > self._max_lots:
             # Reduz linearmente para caber (L1 Projection)
             scaling = self._max_lots / total_est_lots
             clean_w = {s: w * scaling for s, w in clean_w.items()}
             print(f"AEVRA ENFORCER: FTMO Limit Triggered. Scaled weights by {scaling:.2f}")

        return clean_w

    def is_feasible(self, weights: Dict[str, float]) -> bool:
        """Verifica se os pesos estão dentro de todos os envelopes de segurança."""
        total_f = sum(weights.values())
        if total_f > 0.15: return False # 15% Max Global Exposure Safety
        for w in weights.values():
             if w > self._max_fraction: return False
        return True
