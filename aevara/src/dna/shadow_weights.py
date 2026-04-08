# @module: aevara.src.dna.shadow_weights
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Online shadow weight adaptation with gradient clipping, EMA smoothing,
#           bounded memory, and atomic promotion. Integrates with PhantomEngine
#           gradients. Real weights only change via atomic_swap after gate passes.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque

import numpy as np


@dataclass(frozen=True, slots=True)
class GradientBatch:
    """Output do PhantomEngine por ciclo."""
    gradient_vector: Dict[str, float]   # dJ/dw_i
    phantom_rr: float
    alignment_score: float              # [0,1] ghost vs real
    cycle_id: int
    timestamp_ns: int


@dataclass(frozen=True, slots=True)
class ShadowUpdate:
    """Resultado de uma aplicacao de gradiente."""
    agent_id: str
    old_shadow: float
    new_shadow: float
    gradient_applied: float
    ema_value: float


@dataclass(frozen=True, slots=True)
class DNAWeights:
    """Snapshot imutavel de pesos DNA."""
    real_weights: Dict[str, float]
    shadow_weights: Dict[str, float]
    generation: int
    last_promotion_cycle: int


class ShadowWeightManager:
    """
    Gerencia adaptacao de shadow weights com gradientes do PhantomEngine.

    Invariantes:
    - shadow_weights sempre normalizados (sum = 1.0)
    - real_weights so mudam via promote (atomic swap)
    - gradientes clipados em [-clip_bound, clip_bound]
    - EMA smoothing com beta configuravel
    - Bounded memory: update_history maxlen = 500
    """

    def __init__(
        self,
        learning_rate: float = 0.02,
        clip_bound: float = 1.0,
        ema_beta: float = 0.9,
        min_weight: float = 0.01,
        max_weight: float = 0.95,
    ):
        assert 0.0 <= learning_rate <= 1.0
        assert clip_bound > 0.0
        assert 0.0 < ema_beta < 1.0
        assert 0.0 <= min_weight < max_weight <= 1.0

        self._lr = learning_rate
        self._clip_bound = clip_bound
        self._ema_beta = ema_beta
        self._min_w = min_weight
        self._max_w = max_weight

        self._real_weights: Dict[str, float] = {}
        self._shadow_weights: Dict[str, float] = {}
        self._ema_values: Dict[str, float] = {}
        self._generation = 0
        self._last_promotion_cycle = 0
        self._update_history: deque[ShadowUpdate] = deque(maxlen=500)

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def weights(self) -> DNAWeights:
        return DNAWeights(
            real_weights=dict(self._real_weights),
            shadow_weights=dict(self._shadow_weights),
            generation=self._generation,
            last_promotion_cycle=self._last_promotion_cycle,
        )

    def initialize(self, agent_ids: List[str], initial_weights: Optional[Dict[str, float]] = None) -> None:
        """Inicializa pesos reais e shadow como copies."""
        if initial_weights:
            for aid in agent_ids:
                w = initial_weights.get(aid, 1.0 / len(agent_ids))
                self._real_weights[aid] = w
                self._shadow_weights[aid] = w
                self._ema_values[aid] = w
        else:
            uniform = 1.0 / len(agent_ids)
            for aid in agent_ids:
                self._real_weights[aid] = uniform
                self._shadow_weights[aid] = uniform
                self._ema_values[aid] = uniform

    def clip_gradients(self, grad_vec: Dict[str, float]) -> Dict[str, float]:
        """Clipa gradientes em [-clip_bound, clip_bound]."""
        return {k: float(np.clip(v, -self._clip_bound, self._clip_bound)) for k, v in grad_vec.items()}

    def apply_gradient(self, grad_batch: GradientBatch) -> Dict[str, ShadowUpdate]:
        """
        Aplica gradiente clipado + EMA aos shadow weights.
        Retorna dict de updates por agent.
        """
        clipped = self.clip_gradients(grad_batch.gradient_vector)
        updates = {}

        for agent_id, grad in clipped.items():
            if agent_id not in self._shadow_weights:
                continue

            old_shadow = self._shadow_weights[agent_id]
            # Gradient step
            new_shadow = old_shadow + self._lr * grad
            # Clip to bounds
            new_shadow = float(np.clip(new_shadow, self._min_w, self._max_w))
            self._shadow_weights[agent_id] = new_shadow

            # EMA smoothing
            old_ema = self._ema_values.get(agent_id, new_shadow)
            ema = self._ema_beta * old_ema + (1.0 - self._ema_beta) * new_shadow
            self._ema_values[agent_id] = ema

            updates[agent_id] = ShadowUpdate(
                agent_id=agent_id,
                old_shadow=old_shadow,
                new_shadow=new_shadow,
                gradient_applied=grad,
                ema_value=ema,
            )
            self._update_history.append(updates[agent_id])

        # Normalize shadow weights
        self._normalize_shadow()
        return updates

    def ema_update(self, current: Dict[str, float], target: Dict[str, float]) -> Dict[str, float]:
        """EMA suavizacao: ema = beta * current + (1-beta) * target."""
        result = {}
        for k in current:
            if k in target:
                result[k] = float(self._ema_beta * current[k] + (1.0 - self._ema_beta) * target[k])
            else:
                result[k] = current[k]
        return result

    def _normalize_shadow(self) -> None:
        """Normaliza shadow weights to sum to 1.0."""
        total = sum(self._shadow_weights.values())
        if total <= 0:
            n = len(self._shadow_weights)
            if n == 0:
                return
            uniform = 1.0 / n
            self._shadow_weights = {k: uniform for k in self._shadow_weights}
        else:
            self._shadow_weights = {k: v / total for k, v in self._shadow_weights.items()}

    def atomic_swap(self) -> Dict[str, float]:
        """
        Promote shadow -> real. Atomic: all or nothing.
        Returns old real weights (for rollback if needed).
        """
        old_real = dict(self._real_weights)
        self._real_weights = dict(self._shadow_weights)
        self._generation += 1
        return old_real

    def rollback(self, old_weights: Dict[str, float]) -> None:
        """Rollback real weights to previous values."""
        self._real_weights = old_weights

    def save(self, path: str = "aevara/state/dna_weights.json") -> None:
        """Persiste pesos reais e shadow no disco de forma atômica."""
        from aevara.src.memory.checkpoint_serializer import CheckpointSerializer
        state = {
            "real_weights": self._real_weights,
            "shadow_weights": self._shadow_weights,
            "ema_values": self._ema_values,
            "generation": self._generation,
            "last_promotion_cycle": self._last_promotion_cycle
        }
        CheckpointSerializer.serialize_state(state, path)

    def load(self, path: str = "aevara/state/dna_weights.json") -> bool:
        """Carrega pesos do disco se checkpoint existir e for íntegro."""
        from aevara.src.memory.checkpoint_serializer import CheckpointSerializer
        payload = CheckpointSerializer.deserialize_state(path)
        if not payload: return False
        
        self._real_weights = payload.get("real_weights", {})
        self._shadow_weights = payload.get("shadow_weights", {})
        self._ema_values = payload.get("ema_values", {})
        self._generation = payload.get("generation", 0)
        self._last_promotion_cycle = payload.get("last_promotion_cycle", 0)
        return True

    def get_active_weights(self) -> Dict[str, float]:
        """Retorna pesos atualmente ativos (real)."""
        return dict(self._real_weights)

    def get_update_history(self) -> List[ShadowUpdate]:
        return list(self._update_history)
