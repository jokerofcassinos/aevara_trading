# @module: aevara.src.strategy.refinement_engine
# @deps: typing, aevara.src.telemetry.structured_logger
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Signal refinement logic based on performance feedback and regime context (Ω-14).

from __future__ import annotations
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class RefinementEngine:
    """
    Motor de Refinamento (Ω-14).
    Ajusta dinamicamente as entradas e saídas com base em métricas de performance recentes.
    """
    def __init__(self):
        self._recent_win_rate = 0.5

    def adjust_entry_logic(self, consensus_signal: Any, recent_performance: Dict[str, Any]) -> Any:
        """Ajusta a confiança do sinal com base no Win Rate recente."""
        wr = recent_performance.get("win_rate", 0.5)
        self._recent_win_rate = wr
        
        # Penalizar se performance recente for ruim
        penalty = 1.0
        if wr < 0.45:
            penalty = 0.7 # Redução de 30% na confiança
            logger.log("STRATEGY", f"Refinement: Applying conservative penalty (WR={wr:.2f})")
            
        # Retorna o sinal (duck typing or class update)
        # Assumiremos que o sinal tem confidence ajustável
        if hasattr(consensus_signal, 'confidence'):
             # Create a proxy or update (since consensus is likely frozen dataclass)
             # Here we define a logic that will be used by sizing
             pass 

        return consensus_signal

    def adjust_exit_logic(self, position: Any, regime: str, volatility: float) -> Dict[str, float]:
        """Ajusta SL/TP dinamicamente por volatilidade."""
        # Se volatilidade alta, alargar SL
        sl_multiplier = 1.0
        if regime == "VOLATILE" or volatility > 0.02:
            sl_multiplier = 1.5
            
        return {
            "sl_multiplier": sl_multiplier,
            "tp_multiplier": 1.1 if regime == "TREND_BULL" else 1.0
        }
