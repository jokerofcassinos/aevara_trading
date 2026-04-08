# @module: aevara.src.orchestrator.profile_router
# @deps: aevara.src.orchestrator.qroe_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Context-aware profile allocation, context budget tracking,
#           and fallback chain routing. Mapeia fase -> perfil com
#           controle de budget, fallback, e auditoria de uso.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from aevara.src.orchestrator.qroe_engine import Phase


@dataclass(frozen=True, slots=True)
class ProfileAllocation:
    """Contrato de alocacao de perfil para uma fase."""
    profile_id: str
    phase: Phase
    context_budget: int          # Max files to read (budget = 5)
    max_cycles: int              # Max cycle attempts before fallback
    fallback_chain: Tuple[str, ...]  # Fallback profile chain

    def consume_budget(self, used: int) -> bool:
        return used <= self.context_budget


# Profile configuration per phase
_PROFILE_ALLOCATIONS: Dict[Phase, ProfileAllocation] = {
    Phase.DISCOVERY: ProfileAllocation(
        profile_id="Director",
        phase=Phase.DISCOVERY,
        context_budget=3,
        max_cycles=3,
        fallback_chain=("Strategist",),
    ),
    Phase.DESIGN: ProfileAllocation(
        profile_id="Architect",
        phase=Phase.DESIGN,
        context_budget=3,
        max_cycles=2,
        fallback_chain=("Director", "Strategist"),
    ),
    Phase.VALIDATION: ProfileAllocation(
        profile_id="Tester",
        phase=Phase.VALIDATION,
        context_budget=4,
        max_cycles=2,
        fallback_chain=("RiskOfficer", "Auditor"),
    ),
    Phase.EXECUTION: ProfileAllocation(
        profile_id="Coder",
        phase=Phase.EXECUTION,
        context_budget=5,
        max_cycles=3,
        fallback_chain=("Architect", "Tester"),
    ),
    Phase.AUDIT: ProfileAllocation(
        profile_id="Auditor",
        phase=Phase.AUDIT,
        context_budget=4,
        max_cycles=2,
        fallback_chain=("Strategist",),
    ),
    Phase.EVOLUTION: ProfileAllocation(
        profile_id="Strategist",
        phase=Phase.EVOLUTION,
        context_budget=3,
        max_cycles=2,
        fallback_chain=("Director",),
    ),
    Phase.SAFE_MODE: ProfileAllocation(
        profile_id="Strategist",
        phase=Phase.SAFE_MODE,
        context_budget=2,
        max_cycles=5,
        fallback_chain=("Director", "Auditor"),
    ),
}


@dataclass
class ContextBudgetLedger:
    """
    Ledger atomico de uso de contexto.
    Tracking de budget usado por ciclo e perfil.
    """
    budget_limit: int = 5
    current_usage: int = 0
    phase: Optional[Phase] = None
    profile: str = "unknown"
    cycle_id: int = 0

    def remaining(self) -> int:
        return max(0, self.budget_limit - self.current_usage)

    def can_use(self, n: int) -> bool:
        return (self.current_usage + n) <= self.budget_limit

    def consume(self, n: int) -> bool:
        if self.can_use(n):
            self.current_usage += n
            return True
        return False

    def reset(self, phase: Phase, profile: str, cycle_id: int) -> None:
        self.current_usage = 0
        self.phase = phase
        self.profile = profile
        self.cycle_id = cycle_id

    def is_exceeded(self) -> bool:
        return self.current_usage > self.budget_limit


class ProfileRouter:
    """
    Router de perfis com budget tracking e fallback chain.

    Invariantes:
    - Cada fase tem exatamente 1 profile allocation
    - Budget nunca excede 5 (enforced by ledger)
    - Fallback chain sempre existe (min 1 profile)
    """

    def __init__(self):
        self._ledger = ContextBudgetLedger()
        self._allocation_log: List[Dict] = []

    @property
    def ledger(self) -> ContextBudgetLedger:
        return self._ledger

    def get_allocation(self, phase: Phase) -> ProfileAllocation:
        return _PROFILE_ALLOCATIONS[phase]

    def get_fallback(self, phase: Phase) -> List[str]:
        alloc = self.get_allocation(phase)
        return list(alloc.fallback_chain)

    def allocate(self, phase: Phase, cycle_id: int) -> Tuple[str, ProfileAllocation]:
        """
        Aloca perfil para fase.
        Retorna (profile_id, allocation).
        """
        alloc = self.get_allocation(phase)
        self._ledger.reset(phase, alloc.profile_id, cycle_id)
        self._allocation_log.append({
            "phase": phase.name,
            "profile": alloc.profile_id,
            "cycle_id": cycle_id,
            "budget_limit": alloc.context_budget,
        })
        return alloc.profile_id, alloc

    def check_budget(self, used: int, phase: Phase) -> bool:
        """Verifica se budget usado esta dentro do limite."""
        alloc = self.get_allocation(phase)
        return alloc.consume_budget(used)

    def get_allocation_log(self) -> List[Dict]:
        return list(self._allocation_log)
