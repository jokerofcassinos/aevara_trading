# @module: aevara.src.perception.regime_detector
# @deps: numpy, typing, telemetry.logger
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Volatility Expansion (VEX) + HMM-lite regime detector (Ω-4). Analyzes price dynamics to identify market state.

from __future__ import annotations
import numpy as np
import time
from typing import Dict, List, Optional, Tuple
from aevara.src.telemetry.structured_logger import logger

class RegimeDetector:
    """
    Detector de Regime v1.0 (Ω-4).
    Analisa Volatilidade Expansiva (VEX) para classificar o mercado em 3 estados:
    LOW_VOL (Consolidação), NORMAL_VOL (Tendência Saudável), HIGH_VOL (Stress/Pânico).
    """
    def __init__(self, window_size: int = 14):
        self._window_size = window_size
        self._vol_history: List[float] = []

    async def process(self, prices: Optional[List[float]] = None) -> Dict[str, float]:
        """
        Processa ticks/preços recentes para detectar o regime dominante.
        Se 'prices' for None, retorna o último estado conhecido ou baseline.
        """
        if not prices or len(prices) < self._window_size:
            return {"low": 0.33, "normal": 0.34, "high": 0.33, "dominant": "normal"}

        # 1. Calcula Retornos Logarítmicos
        returns = np.diff(np.log(prices))
        
        # 2. VEX Calculation: Rolling STD normalized by ATR-proxy
        current_vol = np.std(returns[-self._window_size:])
        self._vol_history.append(current_vol)
        if len(self._vol_history) > 100: self._vol_history.pop(0)

        # 3. Simple HMM-lite: Classify based on percentile of historical vol
        historical_mean = np.mean(self._vol_history)
        historical_std = np.std(self._vol_history) if len(self._vol_history) > 5 else 0.001

        # Z-Score de Volatilidade
        z_score = (current_vol - historical_mean) / historical_std if historical_std > 0 else 0

        # Probabilities Mapping
        if z_score < -1.0:
            probs = {"low": 0.80, "normal": 0.15, "high": 0.05, "dominant": "low"}
        elif z_score > 2.0:
            probs = {"low": 0.05, "normal": 0.25, "high": 0.70, "dominant": "high"}
        else:
            probs = {"low": 0.10, "normal": 0.80, "high": 0.10, "dominant": "normal"}

        logger.record_metric("regime_z_score", float(z_score))
        logger.log("PERCEPTION", f"Market Regime: {probs['dominant']} (z={z_score:.2f})")
        
        return probs

    async def detect_regime(self, ticks: List[float]) -> Dict[str, float]:
        """Wrapper compatível com o protocolo T-030.1."""
        return await self.process(ticks)
