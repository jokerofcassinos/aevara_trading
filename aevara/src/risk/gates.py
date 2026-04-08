# @module: aevara.src.risk.gates
# @deps: aevara.src.utils.math
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Vetos dinâmicos de risco. Antes de qualquer execucao, o sinal
#           passa por gates que podem veto-lo baseado em drawdown,
#           volatilidade extrema, ou incoerencia.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class VetoReason(str, Enum):
    DRAWDOWN = "drawdown_exceeded"
    VOLATILITY = "volatility_extreme"
    INCOHERENCE = "signal_incoherence"
    EXPOSURE = "max_exposure_reached"
    MANUAL = "manual_override"


@dataclass(frozen=True, slots=True)
class VetoDecision:
    """Resultado do risk gate."""
    vetoed: bool
    reasons: List[VetoReason]
    max_allowed_size: float     # Tamanho maximo permitido (0 = veto total)
    detail: str


@dataclass
class RiskGate:
    """
    Risk gate com veto dinamico.
    Todas as thresholds sao mutaveis (DNA-driven).
    """
    max_drawdown_pct: float = 4.8       # FTMO hard limit (P0)
    max_volatility: float = 0.05        # Volatilidade extrema threshold
    min_coherence_confidence: float = 0.15  # Confianca minima do sinal

    current_drawdown: float = 0.0
    current_volatility: float = 0.0
    signal_confidence: float = 0.0

    def check(
        self,
        drawdown_pct: Optional[float] = None,
        volatility: Optional[float] = None,
        coherence_confidence: Optional[float] = None,
    ) -> VetoDecision:
        """
        Executa risk gate checks.

        Args:
            drawdown_pct: Drawdown atual (% do capital)
            volatility: Volatilidade atual
            coherence_confidence: Confianca do sinal agregado

        Returns:
            VetoDecision com justificativa e tamanho maximo permitido
        """
        dd = drawdown_pct if drawdown_pct is not None else self.current_drawdown
        vol = volatility if volatility is not None else self.current_volatility
        conf = coherence_confidence if coherence_confidence is not None else self.signal_confidence

        reasons: List[VetoReason] = []

        # Check 1: Hard drawdown limit
        if dd >= self.max_drawdown_pct:
            reasons.append(VetoReason.DRAWDOWN)

        # Check 2: Extreme volatility
        if vol >= self.max_volatility:
            reasons.append(VetoReason.VOLATILITY)

        # Check 3: Signal incoherence (zero confidence)
        if conf < self.min_coherence_confidence:
            reasons.append(VetoReason.INCOHERENCE)

        if reasons:
            return VetoDecision(
                vetoed=True,
                reasons=reasons,
                max_allowed_size=0.0,
                detail=f"Vetoed: {[r.value for r in reasons]}",
            )

        # Dynamic sizing reduction based on drawdown proximity
        if dd > self.max_drawdown_pct * 0.6:
            reduction_factor = 1.0 - (dd / self.max_drawdown_pct)
            return VetoDecision(
                vetoed=False,
                reasons=[],
                max_allowed_size=reduction_factor,
                detail=f"Reduced sizing: DD={dd:.2f}%, max_size={reduction_factor:.2f}",
            )

        return VetoDecision(
            vetoed=False,
            reasons=[],
            max_allowed_size=1.0,
            detail="All gates passed",
        )
