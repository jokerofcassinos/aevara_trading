# @module: aevara.src.meta.kg_refinement_proposer
# @deps: typing, time, memory.knowledge_graph
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Automated Knowledge Graph refinement: proposing new connections based on forensic findings and maturity score tracking.

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(slots=True)
class KGRefinementProposal:
    """Proposta de refinamento do Grafo de Conhecimento (v1.0)."""
    source_node: str
    target_node: str
    relation_type: str
    maturity_score: float = 0.0 # [0,1]
    last_update: int = field(default_factory=time.time_ns)
    evidence_count: int = 0

class KGRefinementProposer:
    """
    Propositor de Refinamento de Grafo (v1.0).
    Sugerir novas interfaces latentes ou conexões causais 
    identificadas pelo PostTradeAnalyzer.
    """
    def __init__(self, maturity_threshold: float = 0.7):
        self._proposals: Dict[str, KGRefinementProposal] = {}
        self._threshold = maturity_threshold

    def propose(self, source: str, target: str, relation: str):
        """Adiciona ou reforça uma proposta de conexão no KG."""
        key = f"{source}_{relation}_{target}"
        if key not in self._proposals:
             self._proposals[key] = KGRefinementProposal(source_node=source, target_node=target, relation_type=relation)
        
        prop = self._proposals[key]
        prop.evidence_count += 1
        # Maturidade cresce com evidência: S_m = 1 - exp(-0.2 * N)
        prop.maturity_score = 1.0 - (2.718 ** (-0.2 * prop.evidence_count))
        prop.last_update = time.time_ns()

    def get_mature_proposals(self) -> List[KGRefinementProposal]:
        """Retorna propostas que cruzaram o threshold de maturidade (0.7)."""
        return [p for p in self._proposals.values() if p.maturity_score >= self._threshold]

    def clear(self, proposal: KGRefinementProposal):
        key = f"{proposal.source_node}_{proposal.relation_type}_{proposal.target_node}"
        if key in self._proposals:
             del self._proposals[key]
