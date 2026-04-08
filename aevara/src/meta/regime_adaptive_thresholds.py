# @module: aevara.src.meta.regime_adaptive_thresholds
# @deps: typing, dataclasses, time
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Dynamic threshold calibration: θ_regime = θ_base × f(regime_confidence, volatility, liquidity).

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

class AdaptiveThresholdEngine:
    """
    Motor de Thresholds Adaptativos (v1.0).
    Ajusta dinamicamente sensibilidade de sinais com base no regime:
    θ_regime = θ_base × f(confiança, volatilidade, liquidez).
    """
    def __init__(self, base_thresholds: Dict[str, float]):
        self._base_thresholds = base_thresholds
        self._current_thresholds = base_thresholds.copy()
        
    def compute(self, name: str, regime_context: Dict) -> float:
        """
        Calcula o threshold ótimo para o contexto atual.
        Aumenta o threshold (reduz sensibilidade) sob baixa confiança ou alta vol.
        """
        base = self._base_thresholds.get(name, 0.5)
        conf = regime_context.get("confidence", 0.5)
        vol = regime_context.get("volatility_quintile", 3) / 5.0
        liq = regime_context.get("liquidity_score", 0.5)
        
        # θ_regime = θ_base × (2.0 - conf) × (1.0 + vol)
        # Se vol alta (quintile 5), aumenta threshold para filtrar ruído
        # Se liquidez baixa, aumenta threshold para evitar slippage
        adj = (1.5 - conf) * (1.0 + (vol * 0.5)) * (1.2 - liq)
        
        final_val = base * adj
        self._current_thresholds[name] = final_val
        return final_val

    def recalibrate_base(self, name: str, performance_delta: float) -> None:
        """Ajusta o baseline se a performance estiver consistentemente abaixo do alvo."""
        if performance_delta < 0:
             self._base_thresholds[name] *= 1.05 # Reduz sensibilidade (mais conservador)
        else:
             self._base_thresholds[name] *= 0.95 # Aumenta sensibilidade (mais agressivo)
        
    def get_current(self, name: str) -> float:
        return self._current_thresholds.get(name, 0.5)
