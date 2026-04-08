# @module: aevara.src.dna.promotion_gate
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Validation gate for DNA shadow->real promotion. Histerese anti-oscilacao,
#           thrashing prevention, cooldown mode, e atomic swap enforcement.
#           Promocao so ocorre quando alinhamento >= threshold e RR delta positivo.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np


class GateAction(Enum):
    PROMOTE = "PROMOTE"
    HOLD = "HOLD"
    DEMOTE = "DEMOTE"
    COOLDOWN = "COOLDOWN"


@dataclass(frozen=True, slots=True)
class GateEvaluation:
    """Resultado de avaliacao do promotion gate."""
    action: GateAction
    avg_alignment: float
    avg_rr_delta: float
    thrashing_detected: bool
    cooldown_remaining: int
    reason: str


class PromotionGate:
    """
    Gate de promocao com histerese e anti-oscilacao.

    Invariantes:
    - Promocao so quando avg_alignment >= min_alignment
    - Histerese: promotion_threshold=0.82, demotion_threshold=0.70 (gap 12%)
    - Thrashing: oscilacao >3x em janela de 20 -> cooldown
    - Cooldown suspende promocao por N ciclos
    - Demotion: se avg_alignment < demotion_threshold, volta weights originais
    """

    def __init__(
        self,
        min_alignment: float = 0.82,
        demotion_threshold: float = 0.70,
        min_rr_delta: float = 0.05,
        thrashing_window: int = 20,
        thrashing_max_oscillations: int = 3,
        cooldown_cycles: int = 10,
        history_maxlen: int = 50,
    ):
        assert 0.0 <= demotion_threshold < min_alignment <= 1.0, "Histerese invalida"
        self._min_alignment = min_alignment
        self._demotion_threshold = demotion_threshold
        self._min_rr_delta = min_rr_delta
        self._thrashing_window = thrashing_window
        self._thrashing_max_osc = thrashing_max_oscillations
        self._cooldown_cycles = cooldown_cycles

        self._alignment_history: deque[float] = deque(maxlen=history_maxlen)
        self._rr_delta_history: deque[float] = deque(maxlen=history_maxlen)
        self._cooldown_remaining = 0
        self._last_promoted = False
        self._action_history: deque[GateAction] = deque(maxlen=thrashing_window)

    @property
    def min_alignment(self) -> float:
        return self._min_alignment

    @property
    def demotion_threshold(self) -> float:
        return self._demotion_threshold

    @property
    def cooldown_remaining(self) -> int:
        return self._cooldown_remaining

    def record(self, alignment: float, rr_delta: float) -> None:
        """Registra metricas de ciclo."""
        self._alignment_history.append(alignment)
        self._rr_delta_history.append(rr_delta)

    def evaluate(
        self,
        min_alignment: Optional[float] = None,
        min_rr_delta: Optional[float] = None,
    ) -> GateEvaluation:
        """
        Avalia se promocao e permitida.

        Args:
            min_alignment: Override default threshold
            min_rr_delta: Override default RR delta threshold

        Returns:
            GateEvaluation com acao recomendada
        """
        threshold = min_alignment if min_alignment is not None else self._min_alignment
        rr_req = min_rr_delta if min_rr_delta is not None else self._min_rr_delta

        # Cooldown mode
        if self._cooldown_remaining > 0:
            return GateEvaluation(
                action=GateAction.COOLDOWN,
                avg_alignment=self._avg_alignment(),
                avg_rr_delta=self._avg_rr_delta(),
                thrashing_detected=self._check_thrashing(),
                cooldown_remaining=self._cooldown_remaining,
                reason=f"Cooldown: {self._cooldown_remaining} cycles remaining",
            )

        # Demotion check
        avg_align = self._avg_alignment()
        avg_rr = self._avg_rr_delta()

        if avg_align < self._demotion_threshold:
            self._cooldown_remaining = self._cooldown_cycles
            return GateEvaluation(
                action=GateAction.DEMOTE,
                avg_alignment=avg_align,
                avg_rr_delta=avg_rr,
                thrashing_detected=False,
                cooldown_remaining=self._cooldown_cycles,
                reason=f"Alignment too low: {avg_align:.4f} < {self._demotion_threshold}",
            )

        # Thrashing check
        if self._check_thrashing():
            self._cooldown_remaining = self._cooldown_cycles
            return GateEvaluation(
                action=GateAction.COOLDOWN,
                avg_alignment=avg_align,
                avg_rr_delta=avg_rr,
                thrashing_detected=True,
                cooldown_remaining=self._cooldown_cycles,
                reason=f"Thrashing detected: {self._thrashing_max_osc} oscillations in {self._thrashing_window} window",
            )

        # Promotion check
        if avg_align >= threshold and avg_rr >= rr_req:
            return GateEvaluation(
                action=GateAction.PROMOTE,
                avg_alignment=avg_align,
                avg_rr_delta=avg_rr,
                thrashing_detected=False,
                cooldown_remaining=0,
                reason=f"Promotion approved: alignment={avg_align:.4f}, rr_delta={avg_rr:.4f}",
            )

        return GateEvaluation(
            action=GateAction.HOLD,
            avg_alignment=avg_align,
            avg_rr_delta=avg_rr,
            thrashing_detected=False,
            cooldown_remaining=0,
            reason=f"Holding: alignment={avg_align:.4f} < {threshold} or rr_delta={avg_rr:.4f} < {rr_req}",
        )

    def apply_hysteresis(
        self,
        current_alignment: float,
        promotion_threshold: Optional[float] = None,
        demotion_threshold: Optional[float] = None,
    ) -> str:
        """
        Avaliacao direta com histerese. Retorna "PROMOTE", "HOLD" ou "DEMOTE".
        """
        p_thresh = promotion_threshold if promotion_threshold is not None else self._min_alignment
        d_thresh = demotion_threshold if demotion_threshold is not None else self._demotion_threshold

        if current_alignment >= p_thresh:
            return "PROMOTE"
        elif current_alignment < d_thresh:
            return "DEMOTE"
        else:
            return "HOLD"

    def atomic_swap(self, shadow: Dict[str, float], real: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Atomic swap: real = shadow, but returns old_real for rollback.
        Caller should only call this after gate evaluation returns PROMOTE.
        """
        old_real = dict(real)
        new_real = dict(shadow)
        self._last_promoted = True
        self._action_history.append(GateAction.PROMOTE)
        return new_real, old_real

    def _avg_alignment(self) -> float:
        if not self._alignment_history:
            return 0.0
        return sum(self._alignment_history) / len(self._alignment_history)

    def _avg_rr_delta(self) -> float:
        if not self._rr_delta_history:
            return 0.0
        return sum(self._rr_delta_history) / len(self._rr_delta_history)

    def _check_thrashing(self) -> bool:
        """Detects if alignment oscillated > max times in window."""
        if len(self._alignment_history) < 6:
            return False
        recent = list(self._alignment_history)[-self._thrashing_window:]
        if len(recent) < 6:
            return False

        # Count transitions across threshold
        oscillations = 0
        prev_above = recent[0] >= self._min_alignment
        for val in recent[1:]:
            above = val >= self._min_alignment
            if above != prev_above:
                oscillations += 1
            prev_above = above

        return oscillations >= self._thrashing_max_osc

    def get_alignment_history(self) -> List[float]:
        return list(self._alignment_history)

    def save(self, path: str = "aevara/state/promotion_gate.json") -> None:
        """Persiste estado do gate no disco."""
        from aevara.src.memory.checkpoint_serializer import CheckpointSerializer
        state = {
            "alignment_history": list(self._alignment_history),
            "rr_delta_history": list(self._rr_delta_history),
            "cooldown_remaining": self._cooldown_remaining,
            "last_promoted": self._last_promoted,
            "action_history": [a.value for a in self._action_history]
        }
        CheckpointSerializer.serialize_state(state, path)

    def load(self, path: str = "aevara/state/promotion_gate.json") -> bool:
        """Carrega estado do gate do disco."""
        from aevara.src.memory.checkpoint_serializer import CheckpointSerializer
        payload = CheckpointSerializer.deserialize_state(path)
        if not payload: return False
        
        self._alignment_history = deque(payload.get("alignment_history", []), maxlen=self._alignment_history.maxlen)
        self._rr_delta_history = deque(payload.get("rr_delta_history", []), maxlen=self._rr_delta_history.maxlen)
        self._cooldown_remaining = payload.get("cooldown_remaining", 0)
        self._last_promoted = payload.get("last_promoted", False)
        
        actions = payload.get("action_history", [])
        self._action_history = deque([GateAction(a) for a in actions], maxlen=self._action_history.maxlen)
        return True

    def reset(self) -> None:
        self._alignment_history.clear()
        self._rr_delta_history.clear()
        self._cooldown_remaining = 0
        self._last_promoted = False
        self._action_history.clear()
