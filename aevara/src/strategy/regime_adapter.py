# @module: aevara.src.strategy.regime_adapter
# @deps: typing, aevara.src.telemetry.structured_logger
# @status: IMPLEMENTED_STRATEGIC_v1.0
# @last_update: 2026-04-10
# @summary: Dynamic strategy selection and parameter adaptation based on market regime (Ω-17).

from __future__ import annotations
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class RegimeAdapter:
    """
    Adaptador de Regime (Ω-17).
    Mapeia o estado do mercado detectado para a melhor configuração de estratégia disponível.
    """
    def __init__(self):
        # Mapeamento base Regime -> Config Override
        self._regime_map = {
            "TREND_BULL": {"leverage_factor": 1.2, "logic": "TREND_FOLLOWING", "risk_appetite": "HIGH"},
            "TREND_BEAR": {"leverage_factor": 0.8, "logic": "MEAN_REVERSION", "risk_appetite": "LOW"},
            "RANGING": {"leverage_factor": 1.0, "logic": "SCALPING", "risk_appetite": "MEDIUM"},
            "VOLATILE": {"leverage_factor": 0.5, "logic": "BREAKOUT", "risk_appetite": "CRITICAL"}
        }

    def select_strategy(self, regime: str, available_strategies: List[str]) -> str:
        """Seleciona a lógica de estratégia ótima para o regime atual."""
        cfg = self._regime_map.get(regime, {})
        preferred = cfg.get("logic")
        
        if preferred in available_strategies:
            return preferred
        
        # Fallback para a primeira disponível
        return available_strategies[0] if available_strategies else "BASE_PILOT"

    def adapt_parameters(self, base_params: Dict[str, Any], regime: str) -> Dict[str, Any]:
        """Aplica multiplicadores de regime aos parâmetros base."""
        cfg = self._regime_map.get(regime, {})
        mult = cfg.get("leverage_factor", 1.0)
        
        adapted = dict(base_params)
        for k, v in adapted.items():
            if isinstance(v, (int, float)) and "size" in k.lower() or "limit" in k.lower():
                adapted[k] = v * mult
                
        logger.log("STRATEGY", f"Regime Adaptation: '{regime}' applied (Mult: {mult})")
        return adapted

    def get_risk_profile(self, regime: str) -> str:
        return self._regime_map.get(regime, {}).get("risk_appetite", "MEDIUM")
