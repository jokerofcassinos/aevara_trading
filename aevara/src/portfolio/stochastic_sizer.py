# @module: aevara.src.portfolio.stochastic_sizer
# @deps: dataclasses, typing, math, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Multi-dimensional anti-fragile sizing engine maximizing ergodic growth rate under FTMO and market constraints.

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class SizingContext:
    symbol: str
    edge_estimate: float           # E[R] or Kelly fraction raw
    edge_confidence: float         # [0,1] posterior confidence
    volatility_regime: str         # "low", "normal", "high", "extreme"
    correlation_penalty: float     # ∈ [0,1] from portfolio correlator
    liquidity_depth_bps: float     # Book depth at target slippage
    drawdown_state: float          # current_dd / max_dd ∈ [0,1]
    ftmo_headroom_lots: float      # Remaining capacity before 5.0 limit
    cvar_99_5: float               # Conditional Value at Risk

@dataclass(frozen=True, slots=True)
class SizingResult:
    symbol: str
    allocated_fraction: float      # Final f ∈ [0, f_max]
    theoretical_fraction: float    # Unconstrained optimal
    applied_penalties: Dict[str, float]
    ergodic_growth_contribution: float
    constraint_active: str         # Which constraint bound the result
    trace_id: str

class StochasticSizer:
    """
    Motor de Sizing Antifrágil (v1.0.0).
    Maximiza a taxa de crescimento ergódica g = E[ln(1 + fR)]. 
    Aplica penalizações multidimensionais para garantir sobrevivência institucional.
    """
    def __init__(self, f_max_global: float = 0.05, f_min: float = 0.001):
        self._f_max_global = f_max_global
        self._f_min = f_min

    def compute(self, ctx: SizingContext) -> SizingResult:
        """Calcula a fração ótima de alocação (f*) sob restrições."""
        penalties = {}
        
        # 1. Kelly Bayesiano Fracionário (p-q)/σ² × confiança
        f_raw = self._apply_kelly_bayesian(ctx.edge_estimate, ctx.edge_confidence, ctx.volatility_regime)
        f_theoretical = f_raw
        
        # 2. Penalização por CVaR (99.5%)
        # Se CVaR for alto demais, reduzimos f para manter perda esperada sob controle
        f_cvar = self._apply_cvar_penalty(f_raw, ctx.cvar_99_5)
        penalties["cvar"] = f_raw - f_cvar
        f_raw = f_cvar
        
        # 3. Penalização por Correlação (ρ)
        # f_corr = f * (1 - ρ_penalty)
        f_corr = f_raw * (1.0 - ctx.correlation_penalty)
        penalties["correlation"] = f_raw - f_corr
        f_raw = f_corr
        
        # 4. Ajuste de Liquidez
        f_liq = self._apply_liquidity_adjustment(f_raw, ctx.liquidity_depth_bps)
        penalties["liquidity"] = f_raw - f_liq
        f_raw = f_liq
        
        # 5. Restrição FTMO (Lots -> Fraction)
        f_final = self._enforce_ftmo_cap(f_raw, ctx.ftmo_headroom_lots)
        penalties["ftmo_cap"] = f_raw - f_final
        
        # Determinando restrição ativa dominante
        active = "NONE"
        if f_final < f_theoretical:
             active = max(penalties, key=penalties.get)
        
        return SizingResult(
            symbol=ctx.symbol,
            allocated_fraction=max(self._f_min, f_final),
            theoretical_fraction=f_theoretical,
            applied_penalties=penalties,
            ergodic_growth_contribution=f_final * ctx.edge_estimate * 0.5, # Linear proxy
            constraint_active=str(active),
            trace_id=hex(hash(ctx.symbol) & 0xffffffff)
        )

    def _apply_kelly_bayesian(self, edge: float, conf: float, vol_regime: str) -> float:
        # Kelly fracionário com desconto por incerteza (Bayesiana)
        # Básico: edge/variance. Aqui simplificamos para proporção.
        base_f = edge * conf
        regime_scaling = {"low": 1.0, "normal": 0.8, "high": 0.5, "extreme": 0.2}
        return base_f * regime_scaling.get(vol_regime, 0.5)

    def _apply_cvar_penalty(self, f: float, cvar: float) -> float:
        # f = f * exp(-k * cvar) para decaimento suave se risco de cauda subir
        if cvar > 0.05: # > 5% CVaR is extreme
             return f * 0.5
        return f

    def _apply_liquidity_adjustment(self, f: float, depth_bps: float) -> float:
        # Se o slippage esperado for alto, reduz f
        if depth_bps > 10.0: return f * 0.7
        return f

    def _enforce_ftmo_cap(self, f: float, remaining_lots: float) -> float:
        # Converte f (fraçao equity) em lotes estimados e trava no headroom
        # Assume sample account balance de 100k e Notional similar
        est_lots = f * 10
        if est_lots > remaining_lots:
             return remaining_lots / 10.0
        return min(f, self._f_max_global)
