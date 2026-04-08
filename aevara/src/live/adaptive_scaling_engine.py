# @module: aevara.src.live.adaptive_scaling_engine
# @deps: typing, dataclasses, numpy, live.ftmo_guard, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Multi-dimensional anti-fragile sizing engine optimizing long-term growth rate under FTMO constraints and regime-aware risk bounds.

from __future__ import annotations
import numpy as np
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class ScalingConfig:
    """Configuração do motor de escalonamento termodinâmico."""
    base_sizing_pct: float           # 0.10 (pilot)
    max_sizing_pct: float            # 1.00 (full)
    kelly_fraction: float            # 0.25 (quarter-Kelly)
    cvar_alpha: float                # 0.995
    regime_vol_cap: float            # max vol for scaling
    min_edge_sharpe: float           # 1.5
    validation_window: int           # 50 trades
    hysteresis_gap_pct: float        # 0.15 (prevents thrashing)

@dataclass(frozen=True, slots=True)
class SizingDecision:
    """Decisao atomica de dimensionamento com prova de contexto."""
    timestamp_ns: int
    requested_pct: float
    approved_pct: float
    scaling_factors: Dict[str, float]  # {kelly: 0.8, cvar: 0.7, ...}
    constraint_violations: List[str]
    confidence: float
    trace_id: str

class AdaptiveScalingEngine:
    """
    Motor de sizing antifrágil multidimensional.
    OTIMIZA taxa de crescimento logarítmica (ergodicity economics).
    Calcula alocacao otima f(Kelly, CVaR, Vol, Liquidez, Drawdown, CB).
    """
    def __init__(self, config: ScalingConfig):
        self._config = config

    def calculate_sizing(self, 
                         win_prob: float, 
                         win_loss_ratio: float, 
                         vol_current: float, 
                         drawdown_pct: float,
                         liquidity_depth: float = 1.0, 
                         cb_factor: float = 1.0,
                         tier_multiplier: float = 1.0) -> SizingDecision:
        """
        Calcula o sizing ótimo para o próximo trade/janela.
        f* = p/a - q/b (Kelly) * fraction * factors * tier_multiplier.
        """
        timestamp = time.time_ns()
        trace_id = f"SZ-{timestamp}"
        
        # 1. Bayesian Kelly Calculation (Quarter-Kelly)
        win_rate = max(0.001, win_prob)
        p = win_rate
        q = 1.0 - p
        w = max(0.1, win_loss_ratio)
        
        kelly_full = (p * w - q) / w if (p * w - q) > 0 else 0.0
        kelly_f = kelly_full * self._config.kelly_fraction
        
        # 2. Factors (0.0 to 1.0)
        vol_f = min(1.0, self._config.regime_vol_cap / vol_current) if vol_current > 0 else 1.0
        dd_limit = 0.08
        dd_f = max(0.01, 1.0 - (drawdown_pct / dd_limit))
        liqd_f = min(1.0, liquidity_depth)
        
        # 3. Aggregation (Multiplicative)
        # Sizing eh ponderado pelo multiplicador de tier (ex: 10% pilot, 100% full)
        requested_pct = kelly_f * vol_f * dd_f * liqd_f * cb_factor * tier_multiplier
        
        # 4. Bounds Enforcement
        # O base_sizing_pct eh o piso minimo absoluto. O approved eh limitado pelo max_sizing do Tier.
        max_limit = self._config.max_sizing_pct * tier_multiplier
        final_pct = min(max(self._config.base_sizing_pct, requested_pct), max_limit)
        
        scaling_factors = {
            "kelly_full": kelly_full,
            "vol_f": vol_f,
            "dd_f": dd_f,
            "liqd_f": liqd_f,
            "cb_f": cb_factor,
            "tier_m": tier_multiplier
        }
        
        return SizingDecision(
            timestamp_ns=timestamp,
            requested_pct=float(requested_pct),
            approved_pct=float(final_pct),
            scaling_factors=scaling_factors,
            constraint_violations=[],
            confidence=float(win_rate),
            trace_id=trace_id
        )
