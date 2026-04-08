# @module: aevara.src.strategy.performance_analyzer
# @deps: typing, numpy, aevara.src.telemetry.structured_logger
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Real-time alpha health monitoring, rolling Sharpe and edge decay detection (Ω-16).

from __future__ import annotations
import numpy as np
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class PerformanceAnalyzer:
    """
    Analisador de Performance (Ω-16).
    Detecta degradação de alpha e métricas de eficiência estatística em runtime.
    """
    def __init__(self, sharpe_window: int = 50):
        self.sharpe_window = sharpe_window
        self._returns: List[float] = []

    def add_return(self, ret: float):
        self._returns.append(ret)
        if len(self._returns) > self.sharpe_window * 2:
            self._returns.pop(0)

    def rolling_sharpe(self, window: Optional[int] = None) -> float:
        """Calcula o Sharpe ratio anualizado para a janela informada."""
        w = window or self.sharpe_window
        if len(self._returns) < 5: return 0.0
        
        recent = np.array(self._returns[-w:])
        mean = np.mean(recent)
        std = np.std(recent)
        
        if std == 0: return 0.0
        
        # Anualização simplificada (ex: 252 dias)
        return (mean / std) * np.sqrt(252)

    def expectancy(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calcula a expectativa matemática por trade."""
        return (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))

    def detect_edge_decay(self, metrics: Dict[str, Any], threshold: float = -0.02) -> bool:
        """Verifica se há tendência negativa sustentada na performance."""
        # Simplificacao: Checar se o Sharpe rolling caiu abaixo de um limite critico
        current_sharpe = metrics.get("rolling_sharpe", 0.0)
        is_decaying = current_sharpe < 0.5 # Threshold de decaimento severo
        
        if is_decaying:
            logger.log("WARNING", f"EDGE DECAY DETECTED: Rolling Sharpe {current_sharpe:.2f} < 0.5")
            
        return is_decaying

    def get_summary_metrics(self) -> Dict[str, Any]:
        return {
            "rolling_sharpe": self.rolling_sharpe(),
            "returns_count": len(self._returns),
            "is_stable": self.rolling_sharpe() > 1.0
        }
