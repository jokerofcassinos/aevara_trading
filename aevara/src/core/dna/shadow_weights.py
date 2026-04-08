# @module: aevara.src.core.dna.shadow_weights
# @deps: aevara.src.utils.math, aevara.src.core.invariants
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Shadow weights para adaptacao de agentes. Pessos de agentes são
#           ajustados online via gradiente de performance, mas só são promovidos
#           após validação em janela contrafactual.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True, slots=True)
class ShadowUpdate:
    """Resultado de uma atualização de shadow weight."""
    agent_id: str
    old_weight: float
    new_weight: float
    gradient: float
    performance_delta: float
    promoted: bool


@dataclass
class ShadowWeightManager:
    """
    Gerencia shadow weights para adaptação de agentes.
    Mantém dois conjuntos de pesos: active (em uso) e shadow (em teste).
    """
    active_weights: Dict[str, float] = field(default_factory=dict)
    shadow_weights: Dict[str, float] = field(default_factory=dict)
    learning_rate: float = 0.02
    min_weight: float = 0.01
    max_weight: float = 0.95

    def initialize(self, agents: list[str], initial_weights: Dict[str, float]) -> None:
        """Initialize active and shadow weights."""
        for agent_id in agents:
            w = initial_weights.get(agent_id, 1.0 / len(agents))
            self.active_weights[agent_id] = w
            self.shadow_weights[agent_id] = w

    def update_shadow(self, agent_id: str, gradient: float) -> ShadowUpdate:
        """
        Update shadow weight via gradient step: w_shadow += eta * grad
        Weight is clipped to [min_weight, max_weight].
        """
        old_shadow = self.shadow_weights.get(agent_id, 0.0)
        new_shadow = old_shadow + self.learning_rate * gradient
        new_shadow = max(self.min_weight, min(self.max_weight, new_shadow))
        self.shadow_weights[agent_id] = new_shadow

        return ShadowUpdate(
            agent_id=agent_id,
            old_weight=old_shadow,
            new_weight=new_shadow,
            gradient=gradient,
            performance_delta=gradient * self.learning_rate,
            promoted=False,
        )

    def normalize_shadow(self) -> Dict[str, float]:
        """Normalize shadow weights to sum to 1.0."""
        total = sum(self.shadow_weights.values())
        if total <= 0:
            return {k: 1.0 / len(self.shadow_weights) for k in self.shadow_weights}
        return {k: v / total for k, v in self.shadow_weights.items()}

    def promote_shadow(self) -> Dict[str, ShadowUpdate]:
        """
        Promote shadow weights to active. Returns dict of updates.
        Should be called after validation window passes.
        """
        updates = {}
        for agent_id, shadow_w in self.shadow_weights.items():
            old_active = self.active_weights.get(agent_id, 0.0)
            self.active_weights[agent_id] = shadow_w
            updates[agent_id] = ShadowUpdate(
                agent_id=agent_id,
                old_weight=old_active,
                new_weight=shadow_w,
                gradient=0.0,
                performance_delta=shadow_w - old_active,
                promoted=True,
            )
        return updates
