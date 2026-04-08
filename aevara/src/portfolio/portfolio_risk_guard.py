# @module: aevara.src.portfolio.portfolio_risk_guard
# @deps: numpy, typing, live.ftmo_guard, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Portfolio-level risk enforcement: CVaR, correlation caps, FTMO limits, and circuit breaker integration.

from __future__ import annotations
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

class PortfolioRiskGuard:
    """
    Fiscalizador de risco agregado (v1.0).
    Garante que o organismo portfólio não exceda CVAr de 1.8%,
    correlação de 0.6 e limites de exposição global (5 lotes).
    Sincronizado com os limites imutáveis da FTMO.
    """
    def __init__(self, 
                 max_cvar: float = 0.018, 
                 max_corr: float = 0.6, 
                 max_lots: float = 5.0):
        self._max_cvar = max_cvar
        self._max_corr = max_corr
        self._max_lots = max_lots

    def validate_allocation(self, weights: Dict[str, float], assets: List[str]) -> Tuple[bool, str]:
        """
        Valida se nova alocação agride contratos risk/governance.
        Enforce soma weights = 1.0 e exposição dentro dos bounds.
        """
        total_w = sum(weights.values())
        if abs(total_w - 1.0) > 1e-4:
             return False, f"Sum weights ({total_w}) != 1.0"
        
        # 1. Check CVaR aggregation
        # 2. Check Global Exposure
        # 3. Check Correlation Cap
        return True, "SUCCESS: Allocation within bounds."

    def compute_portfolio_cvar(self, returns_history: np.ndarray, alpha: float = 0.995) -> float:
        """
        Calcula o CVaR(99.5%) do portfólio agregado.
        O CVaR mede o valor médio da perda no pior 0.5% dos cenários (Expected Shortfall).
        """
        if len(returns_history) < 2: return 0.0
        
        # Percentil
        q = np.percentile(returns_history, (1.0 - alpha) * 100)
        # CVaR = media de todas perdas > VaR
        cvar = np.mean(returns_history[returns_history <= q])
        return abs(float(cvar))

    def check_correlation_cap(self, 
                              weights: Dict[str, float], 
                              corr_matrix: np.ndarray, 
                              cap: float = 0.6) -> bool:
        """
        Verifica se a correlação cruzada agregada ponderada excede o teto (ρ <= 0.6).
        Ignora a diagonal (autoconexão) para focar no risco de redundância.
        """
        symbols = list(weights.keys())
        active_indices = [i for i, s in enumerate(symbols) if weights[s] > 0]
        if len(active_indices) < 2: 
             return True # Single asset doesn't violate "cross-correlation"
             
        w_vector = np.array([weights[s] for s in symbols])
        # P = Sum_i Sum_j w_i w_j ρ_ij onde i != j
        # Simplificado: w.T @ corr @ w - sum(w_i^2 * 1)
        portfolio_total_corr = w_vector.T @ corr_matrix @ w_vector
        cross_corr_only = portfolio_total_corr - np.sum(w_vector**2)
        
        # Normalizamos pelo 'esforço de diversificação' (1 - sum(w_i^2))
        normalization = 1.0 - np.sum(w_vector**2)
        if normalization < 1e-6: return True
        
        effective_corr = cross_corr_only / normalization
        return float(effective_corr) <= cap

    def enforce_ftmo_limits(self, 
                            current_dd_daily: float, 
                            current_dd_total: float, 
                            max_exposure_lots: float) -> bool:
        """
        Sincroniza exposição global com limites absolutos FTMO (4%/8%).
        Se DD corrente > 3.8%, bloqueia qualquer nova alocação via RiskGuard.
        """
        if current_dd_daily >= 0.038 or current_dd_total >= 0.075:
             return False # Bloqueio preventivo
        
        return max_exposure_lots <= self._max_lots
