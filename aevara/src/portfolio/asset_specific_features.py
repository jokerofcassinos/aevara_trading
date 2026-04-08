# @module: aevara.src.portfolio.asset_specific_features
# @deps: typing, dataclasses, time
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Symbol-tailored feature pipelines (vol scaling, funding normalization, session profiles, microstructure normalization) for multi-asset portfolios.

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

class AssetSpecificFeatures:
    """
    Normalizador de Microestrutura (v1.0.0).
    Ajusta features de BTC/ETH/SOL conforme especificações de sessão e funding.
    Garante que os alphas operem em escala comum de risco/volatilidade.
    """
    def __init__(self, asset_configs: Dict[str, Dict]):
        self._configs = asset_configs

    def compute_vol_weighted_feature(self, symbol: str, raw_val: float, hour_utc: int) -> float:
        """Ajusta a amplitude da feature baseada no perfil de volatilidade da sessão."""
        config = self._configs.get(symbol, {})
        session_p = config.get("session_profile", {})
        
        # Encontra range de horas
        scale = 1.0
        for h_range, s_val in session_p.items():
             start, end = map(int, h_range.split("_"))
             if start <= hour_utc < end:
                  scale = s_val
                  break
        
        # Feature_norm = Raw / Session_Vol
        return raw_val / (scale or 1.0)

    def normalize_funding_drag(self, symbol: str, funding_rate: float) -> float:
        """Penaliza o alpha se o custo de carregamento (funding) for excessivo."""
        config = self._configs.get(symbol, {})
        factor = config.get("funding_normalization_factor", 1.0)
        
        # Impacto do custo na expectativa de retorno (bps)
        return funding_rate * factor * 100.0

    def compute_tce_buffer(self, symbol: str, volatility: float) -> float:
        """Calcula o buffer de custo de transação (TCE) ideal."""
        config = self._configs.get(symbol, {})
        base_budget = config.get("tce_budget_bps", 2.0)
        
        # Margin de erro proporcional a volatilidade
        return base_budget * (1.0 + volatility)
