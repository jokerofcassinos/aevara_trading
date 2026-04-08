# @module: aevara.src.core.dna.promotion_gate
# @deps: aevara.src.core.dna.shadow_weights
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Gate de promocao para shadow weights. So promove quando
#           alignment >= threshold por janela minima de observacao.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True, slots=True)
class WindowObservation:
    """Single observation in the validation window."""
    timestamp_ns: int
    shadow_sharpe: float
    active_sharpe: float
    alignment: float  # correlation between shadow and active decisions


@dataclass
class PromotionGate:
    """Validates shadow weights against active weights over a window."""
    min_window_size: int = 50       # Minimum observations needed
    min_alignment: float = 0.82     # Minimum correlation for promotion
    min_sharpe_improvement: float = 0.1  # Minimum Sharpe delta
    observations: List[WindowObservation] = field(default_factory=list)

    def add_observation(self, obs: WindowObservation) -> None:
        self.observations.append(obs)

    def is_ready(self) -> bool:
        return len(self.observations) >= self.min_window_size

    def evaluate(self) -> tuple[bool, str]:
        """
        Evaluate promotion criteria.
        Returns (promoted, reason).
        """
        if not self.is_ready():
            return False, f"Window not full: {len(self.observations)}/{self.min_window_size}"

        obs = self.observations[-self.min_window_size:]
        alignments = [o.alignment for o in obs]
        sharpe_deltas = [o.shadow_sharpe - o.active_sharpe for o in obs]

        avg_alignment = sum(alignments) / len(alignments)
        avg_sharpe_delta = sum(sharpe_deltas) / len(sharpe_deltas)

        if avg_alignment < self.min_alignment:
            return False, f"Alignment too low: {avg_alignment:.4f} < {self.min_alignment}"

        if avg_sharpe_delta < self.min_sharpe_improvement:
            return False, f"Insufficient Sharpe improvement: {avg_sharpe_delta:.4f} < {self.min_sharpe_improvement}"

        return True, f"Promotion approved: alignment={avg_alignment:.4f}, Sharpe_delta={avg_sharpe_delta:.4f}"

    def reset(self) -> None:
        self.observations.clear()
