# @module: aevara.src.agents.base
# @deps: aevara.src.utils.math
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Template de agente com contrato de I/O. Todo agente deve implementar
#           get_signal() retornando log-odds com confidence.

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True, slots=True)
class AgentSignal:
    """Contrato de saida de todo agente."""
    agent_id: str
    logodds: float          # Sinal em espaco log-odds
    confidence: float       # [0, 1] - confianca no sinal
    metadata: Dict[str, Any]  # Dados auxiliares para auditoria


class BaseAgent(ABC):
    """
    Template base para agentes. Cada agente:
    1. Recebe dados normalizados (features)
    2. Produz um sinal em espaco log-odds
    3. Reporta confidence calibrada
    """
    agent_id: str
    _min_logodds: float = -4.5
    _max_logodds: float = +4.5

    @abstractmethod
    def get_signal(self, features: Dict[str, float]) -> AgentSignal:
        """
        Calcula sinal em log-odds a partir de features normalizadas.

        Args:
            features: Dic de features normalizadas

        Returns:
            AgentSignal com logodds e confidence
        """
        ...

    def _clip_logodds(self, L: float) -> float:
        return max(self._min_logodds, min(self._max_logodds, L))

    def _confidence_from_logodds(self, L: float) -> float:
        """Confidence = |L| / L_max, bounded a [0, 1]."""
        return min(1.0, abs(L) / self._max_logodds)
