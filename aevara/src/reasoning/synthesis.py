# @module: aevara.src.reasoning.synthesis
# @deps: typing, numpy
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Signal synthesis engine for weighted belief aggregation and divergence tracking (Ψ-3).

from __future__ import annotations
import numpy as np
from typing import Any, Dict, List, Optional

class Synthesis:
    """
    Síntese Cognitiva (Ψ-3).
    Agrega múltiplos sinais e crenças em uma decisão executiva única.
    """
    def __init__(self):
        pass

    async def aggregate_signals(self, 
                                 signals: List[Dict[str, float]], 
                                 weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """
        Pondera e normaliza múltiplos inputs para gerar um consenso.
        signals: Lista de dicts com {'direction': -1/1, 'confidence': 0-1}
        """
        if not signals:
            return {"final_direction": 0.0, "confidence": 0.0, "divergence_penalty": 0.0}

        if weights is None:
            weights = {str(i): 1.0 / len(signals) for i in range(len(signals))}

        weighted_direction = 0.0
        confidences = []

        for i, sig in enumerate(signals):
            w = weights.get(str(i), 0.0)
            weighted_direction += sig['direction'] * sig['confidence'] * w
            confidences.append(sig['direction'])

        # Divergence: Desvio padrão das direções (mecanismo anti-conflito)
        divergence = np.std(confidences) if len(confidences) > 1 else 0.0
        
        # Penalidade de Divergência: reduz confiança se agentes discordarem
        final_confidence = np.clip(abs(weighted_direction) * (1.0 - divergence), 0.0, 1.0)
        final_direction = 1.0 if weighted_direction > 0 else -1.0
        
        return {
            "final_direction": float(final_direction),
            "confidence": float(final_confidence),
            "divergence_penalty": float(divergence)
        }

    async def process(self, *args, **kwargs) -> Dict[str, float]:
        """Pass-through para o cognitive loop."""
        return await self.aggregate_signals([])
