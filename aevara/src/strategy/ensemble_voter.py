# @module: aevara.src.strategy.ensemble_voter
# @deps: typing, dataclasses, numpy
# @status: IMPLEMENTED_STRATEGIC_v1.0
# @last_update: 2026-04-10
# @summary: Signal aggregation engine with weighting and divergence penalty (Ψ-3).

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

@dataclass(frozen=True)
class ConsensusSignal:
    symbol: str
    direction: int # 1 (BUY), -1 (SELL), 0 (FLAT)
    confidence: float
    edge: float
    divergence_penalty: float
    contributing_strategies: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

class EnsembleVoter:
    """
    Votador Ensemble (Ψ-3).
    Agrega sinais de múltiplas fontes com ponderação dinâmica e penalidade de entropia/divergência.
    """
    def __init__(self, divergence_threshold: float = 0.5):
        self.divergence_threshold = divergence_threshold

    def aggregate_signals(self, signals: List[Any], weights: Optional[Dict[str, float]] = None) -> Optional[ConsensusSignal]:
        """
        Gera um sinal de consenso baseado em direções ponderadas.
        """
        if not signals:
            return None

        symbol = signals[0].symbol
        weighted_direction = 0.0
        total_weight = 0.0
        
        # Use simple equal weights if not provided
        if not weights:
            weights = {getattr(sig, 'strategy_id', f"S{i}"): 1.0 for i, sig in enumerate(signals)}

        directions = []
        weighted_edge = 0.0
        for sig in signals:
            sid = getattr(sig, 'strategy_id', 'unknown')
            w = weights.get(sid, 0.1)
            
            # Map BUY -> 1, SELL -> -1, FLAT -> 0
            dir_val = 1 if sig.side == "BUY" else -1 if sig.side == "SELL" else 0
            weighted_direction += dir_val * w * sig.confidence
            weighted_edge += getattr(sig, 'edge', 0.0) * w
            total_weight += w
            directions.append(dir_val)

        if total_weight == 0:
            return None

        avg_direction = weighted_direction / total_weight
        final_direction = 1 if avg_direction > 0.2 else -1 if avg_direction < -0.2 else 0
        
        # Calculo de divergência (Entropy-like)
        # Se os sinais apontam para lados opostos, a divergência é alta
        std_dev = np.std(directions) if len(directions) > 1 else 0.0
        penalty = 1.0 - min(1.0, std_dev)
        
        final_confidence = abs(avg_direction) * penalty
        
        # Log strategic decision
        logger.log("STRATEGY", f"Ensemble Consensus: {symbol} | Dir: {final_direction} | Conf: {final_confidence:.2f} | Penalty: {penalty:.2f}")

        return ConsensusSignal(
            symbol=symbol,
            direction=final_direction,
            confidence=final_confidence,
            edge=weighted_edge / total_weight,
            divergence_penalty=1.0 - penalty,
            contributing_strategies=list(weights.keys()),
            metadata={"raw_weighted_dir": avg_direction}
        )
