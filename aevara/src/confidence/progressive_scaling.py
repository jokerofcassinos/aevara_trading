# @module: aevara.src.confidence.progressive_scaling
# @deps: typing, dataclasses
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Progressive scaling substrate based on confidence signals (Ω-33). Tiered exposure mapping.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

@dataclass(frozen=True, slots=True)
class ScalingContext:
    initial_lot: float
    confidence_score: float # [0, 1]
    confidence_history: List[float] = field(default_factory=list)

class ProgressiveScaling:
    """
    Substrato de Scaling Progressivo (Ω-33).
    Ajusta a exposição com base em patamares discretos de confiança e detecta decaimento de sinal.
    """
    def __init__(self, decay_threshold: float = 0.15):
        self.decay_threshold = decay_threshold

    def adjust_exposure(self, context: ScalingContext) -> float:
        """
        Mapeia confiança em multiplicadores de exposição e aplica rollback se houver decaimento.
        """
        c = context.confidence_score
        
        # Mapeamento por Tiers
        if c < 0.6: 
            multiplier = 0.5 # Redução agressiva para sinais fracos
        elif 0.6 <= c < 0.8: 
            multiplier = 1.0 # Exposição padrão
        else: 
            multiplier = 1.5 # Expansão para alta confiança
            
        # Detecção de Decaimento (Rollback)
        if len(context.confidence_history) >= 5:
            recent_avg = sum(context.confidence_history[-5:]) / 5.0
            if (recent_avg - c) > self.decay_threshold:
                logger.log("SCALING", f"Confidence decay detected ({recent_avg:.2f} -> {c:.2f}). Forcing fallback.")
                multiplier = 0.25 # Fallback emergencial
        
        final_lot = context.initial_lot * multiplier
        return float(final_lot)

    async def calculate_target_size(self, context: ScalingContext) -> float:
        """Ponto de entrada assíncrono para integração no loop cognitivo."""
        return self.adjust_exposure(context)
