# @module: aevara.src.orchestrator.qroe_engine
# @deps: aevara.src.memory.context_library, aevara.src.core.invariants
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Deterministic QROE state machine with explicit phase transitions,
#           gate validation, hysteresis buffer, and no backward jumps.
#           Zero ambiguidade. Zero drift. Zero blocking.

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from aevara.src.core.invariants import InvariantResult


class Phase(Enum):
    """
    Fases do ciclo QROE.
    Transicao segue DAG linear: DISCOVERY -> DESIGN -> VALIDATION ->
    EXECUTION -> AUDIT -> EVOLUTION -> (loop to DISCOVERY or SAFE_MODE).
    Backward jump so via SAFE_MODE intermediario.
    """
    DISCOVERY = auto()
    DESIGN = auto()
    VALIDATION = auto()
    EXECUTION = auto()
    AUDIT = auto()
    EVOLUTION = auto()
    SAFE_MODE = auto()


_PHASE_ORDER = [
    Phase.DISCOVERY,
    Phase.DESIGN,
    Phase.VALIDATION,
    Phase.EXECUTION,
    Phase.AUDIT,
    Phase.EVOLUTION,
    Phase.SAFE_MODE,
]

# Gate names corresponding to each transition
_GATE_CONFIG = {
    "G1": "Schema Integrity",
    "G2": "Phantom Fidelity (Memory)",
    "G3": "Coherence Stability",
    "G4": "Async Safety",
}

# Hysteresis: max oscillations before SAFE_MODE trigger
_MAX_OSCILLATIONS = 3


@dataclass(frozen=True, slots=True)
class GateValidation:
    """Resultado de validacao de um gate individual."""
    gate_id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class StateTransition:
    """
    Objeto imutavel representando uma transicao de fase.
    Valida gates, context budget, e permissoes de transicao.
    """
    from_phase: Phase
    to_phase: Phase
    gate_results: Dict[str, bool]
    context_budget_used: int
    hysteresis_counter: int = 0
    oscillation_detected: bool = False

    def is_valid(self) -> bool:
        return (
            all(self.gate_results.values())
            and self.gate_results
            and self.context_budget_used <= 5
            and self._transition_allowed(self.from_phase, self.to_phase)
            and not self.oscillation_detected
        )

    @staticmethod
    def _transition_allowed(current: Phase, candidate: Phase) -> bool:
        """
        DAG explicit: avancar para proxima fase, EVOLUTION->DISCOVERY loop,
        SAFE_MODE->DISCOVERY reset, or jump to SAFE_MODE from any phase.
        Backward jump so via SAFE_MODE intermediario.
        """
        curr_idx = _PHASE_ORDER.index(current)
        cand_idx = _PHASE_ORDER.index(candidate)
        # Forward only (next), EVOLUTION->DISCOVERY loop, or jump to SAFE_MODE
        if current == Phase.EVOLUTION and candidate == Phase.DISCOVERY:
            return True
        if current == Phase.SAFE_MODE and candidate == Phase.DISCOVERY:
            return True
        return cand_idx == curr_idx + 1 or candidate == Phase.SAFE_MODE

    def get_failed_gates(self) -> List[str]:
        return [gid for gid, passed in self.gate_results.items() if not passed]

    @staticmethod
    def all_gates_pass() -> Dict[str, bool]:
        return {"G1": True, "G2": True, "G3": True, "G4": True}


@dataclass(frozen=True, slots=True)
class CycleState:
    """Estado imutavel de um ciclo QROE."""
    cycle_id: int
    phase: Phase
    active_profile: str
    gate_results: Dict[str, bool]
    context_budget_used: int
    hysteresis_counter: int
    transition: Optional[StateTransition]
    error: str = ""


class QROEEngine:
    """
    Motor de estado deterministico do QROE.

    Invariantes:
    - Transicoes sao sempre para frente (ou SAFE_MODE)
    - Context budget nunca excede 5
    - Oscilacao > MAX_OSCILLATIONS -> SAFE_MODE
    - Backward jump so via SAFE_MODE
    """

    def __init__(self):
        self._current_phase = Phase.DISCOVERY
        self._cycle_id = 0
        self._hysteresis_counter = 0
        self._oscillation_history: List[Phase] = []
        self._history: List[CycleState] = []

    @property
    def current_phase(self) -> Phase:
        return self._current_phase

    @property
    def cycle_id(self) -> int:
        return self._cycle_id

    def get_next_phase(self) -> Phase:
        """Determina proxima fase com base no DAG."""
        if self._current_phase == Phase.SAFE_MODE:
            return Phase.DISCOVERY  # Reset after safe mode
        if self._current_phase == Phase.EVOLUTION:
            return Phase.DISCOVERY  # Loop back
        idx = _PHASE_ORDER.index(self._current_phase)
        return _PHASE_ORDER[idx + 1]

    def execute_transition(
        self,
        gate_results: Dict[str, bool],
        context_budget_used: int = 0,
    ) -> StateTransition:
        """
        Executa validacao e transicao de fase.

        Args:
            gate_results: Dict de gate_id -> passed
            context_budget_used: Budget usado neste ciclo

        Returns:
            StateTransition com resultado da validacao
        """
        from_phase = self._current_phase
        to_phase = self.get_next_phase()

        # Check hysteresis
        self._oscillation_history.append(to_phase)
        if len(self._oscillation_history) > 10:
            self._oscillation_history = self._oscillation_history[-10:]
        oscillation = self._check_oscillation()

        # If oscillating, force SAFE_MODE
        if oscillation:
            to_phase = Phase.SAFE_MODE

        # Check if gates pass for non-SAFE_MODE transitions
        all_pass = all(gate_results.values()) if gate_results else False

        transition = StateTransition(
            from_phase=from_phase,
            to_phase=to_phase,
            gate_results=gate_results,
            context_budget_used=context_budget_used,
            hysteresis_counter=self._hysteresis_counter,
            oscillation_detected=oscillation,
        )

        if transition.is_valid():
            self._current_phase = to_phase
            self._cycle_id += 1
            self._history.append(CycleState(
                cycle_id=self._cycle_id,
                phase=to_phase,
                active_profile=self.get_active_profile(to_phase),
                gate_results=gate_results,
                context_budget_used=context_budget_used,
                hysteresis_counter=self._hysteresis_counter,
                transition=transition,
            ))
        else:
            failed = transition.get_failed_gates()
            if "context_budget" in [g for g in failed] or context_budget_used > 5:
                to_phase = Phase.SAFE_MODE
                self._current_phase = Phase.SAFE_MODE
            elif failed:
                # Gate failure: stay in current phase
                self._history.append(CycleState(
                    cycle_id=self._cycle_id,
                    phase=from_phase,
                    active_profile=self.get_active_profile(from_phase),
                    gate_results=gate_results,
                    context_budget_used=context_budget_used,
                    hysteresis_counter=self._hysteresis_counter,
                    transition=transition,
                    error=f"Gate failure: {failed}",
                ))

        return transition

    def force_safe_mode(self, reason: str = "Manual override") -> StateTransition:
        """Forca entrada em SAFE_MODE. Reset do counter de histerese."""
        from_phase = self._current_phase
        self._current_phase = Phase.SAFE_MODE
        self._hysteresis_counter = 0
        self._oscillation_history.clear()

        transition = StateTransition(
            from_phase=from_phase,
            to_phase=Phase.SAFE_MODE,
            gate_results={},
            context_budget_used=0,
            hysteresis_counter=0,
            oscillation_detected=False,
        )
        self._cycle_id += 1
        self._history.append(CycleState(
            cycle_id=self._cycle_id,
            phase=Phase.SAFE_MODE,
            active_profile="Strategist",  # Strategist handles safe mode
            gate_results={},
            context_budget_used=0,
            hysteresis_counter=0,
            transition=transition,
            error=reason,
        ))
        return transition

    def reset_to_discovery(self) -> Phase:
        """Reset para DISCOVERY (apos SAFE_MODE resolucao)."""
        self._current_phase = Phase.DISCOVERY
        self._hysteresis_counter = 0
        self._oscillation_history.clear()
        return self._current_phase

    def _check_oscillation(self) -> bool:
        """Detecta se fase alternou > MAX_OSCILLATIONS vezes nos ultimos 10 ciclos."""
        if len(self._oscillation_history) < 6:
            return False
        recent = self._oscillation_history[-6:]
        distinct_phases = len(set(recent))
        is_oscillating = distinct_phases <= 2
        if is_oscillating:
            self._hysteresis_counter += 1
        else:
            self._hysteresis_counter = 0
        return self._hysteresis_counter >= _MAX_OSCILLATIONS

    def get_active_profile(self, phase: Optional[Phase] = None) -> str:
        """Mapeamento fase -> perfil ativo principal."""
        phase = phase or self._current_phase
        profile_map = {
            Phase.DISCOVERY: "Director",
            Phase.DESIGN: "Architect",
            Phase.VALIDATION: "Tester",
            Phase.EXECUTION: "Coder",
            Phase.AUDIT: "Auditor",
            Phase.EVOLUTION: "Strategist",
            Phase.SAFE_MODE: "Strategist",
        }
        return profile_map.get(phase, "Director")

    def get_gateway_config(self) -> Dict[str, str]:
        return dict(_GATE_CONFIG)

    def get_history(self) -> List[CycleState]:
        return list(self._history)

    def get_transition_dag(self) -> str:
        """Retorna representacao textual do DAG de transicoes."""
        return " -> ".join(p.name for p in _PHASE_ORDER[:-1]) + " -> (loop)"
