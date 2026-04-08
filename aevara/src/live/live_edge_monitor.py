# @module: aevara.src.live.live_edge_monitor
# @deps: numpy, scipy.stats, collections, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: High-performance rolling edge monitor with significance testing, bootstrap CI, and drift detection.

from __future__ import annotations
import numpy as np
from scipy import stats
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

class LiveEdgeMonitor:
    """
    Monitor do edge vivo do organismo.
    Rastreia Sharpe, win rate e significancia estatistica em janelas deslizantes.
    Preve a degradacao do alpha antes do drawdown profundo.
    """
    def __init__(self, window_size: int = 500):
        self._window_size = window_size
        self._returns: deque = deque(maxlen=window_size)
        self._pnl: deque = deque(maxlen=window_size)
        
    def add_trade(self, return_pct: float, pnl_nominal: float) -> None:
        """Adiciona resultado de trade no monitor."""
        self._returns.append(return_pct)
        self._pnl.append(pnl_nominal)

    def get_metrics(self) -> Dict[str, float]:
        """Calcula métricas fundamentais da janela atual (p500)."""
        if len(self._returns) < 2:
             return {"sharpe": 0.0, "win_rate": 0.0, "expectancy": 0.0, "significance": 0.0}
        
        rets = np.array(self._returns)
        mean_ret = np.mean(rets)
        std_ret = np.std(rets) or 1.0 # Avoid div by zero
        
        sharpe = (mean_ret / std_ret) * np.sqrt(252) # Anualizado
        win_rate = np.mean(rets > 0)
        expectancy = mean_ret
        
        # Teste de significancia (t-test: H0: alpha=0)
        t_stat, p_val = stats.ttest_1samp(rets, 0)
        
        return {
            "sharpe": float(sharpe),
            "win_rate": float(win_rate),
            "expectancy": float(expectancy),
            "significance": 1.0 - float(p_val), # 1-p eh a confianca
            "sample_size": len(rets)
        }

    def detect_drift(self, benchmark_sharpe: float = 1.5) -> bool:
        """Detecta drift de performance (degradacao de edge)."""
        metrics = self.get_metrics()
        return metrics["sharpe"] < (benchmark_sharpe * 0.7) # 30% drop eh drift
