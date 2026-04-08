# @module: aevara.src.interfaces.ocl_parser
# @deps: typing, re, dataclasses, time
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: OCE-TE command decoder: natural language -> structured intent -> QROE dispatch.

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class QROEDispatch:
    """Intencao estruturada resultante do parsing OCE-TE."""
    intent: str               # e.g. "PAUSE", "RESUME", "THRESHOLD_UPDATE", "QUERY"
    spectrum: Dict[str, float] # (Literal, Emocional, Estrategico, Urgencia, Completude, Impacto, Expertise)
    params: Dict[str, Any]
    raw_input: str
    is_valid: bool

class OCLParser:
    """
    Decodifica comandos em linguagem natural do CEO atraves de parsing semantico OCE-TE.
    Extrai intencao, urgencia e impacto para roteamento deterministico.
    """
    def __init__(self):
        self._intents_patterns = {
            "PAUSE": r"(parar|pausa|pause|stop|halt|interrompe)",
            "RESUME": r"(retomar|resume|start|voltar|iniciar)",
            "THRESHOLD_UPDATE": r"(ajustar|mudar|set|update|alterar|threshold|config|size|volume)",
            "QUERY": r"(status|info|check|relatorio|como esta|balanco|metrics|metrica)"
        }

    def decode(self, raw_text: str) -> QROEDispatch:
        text = raw_text.lower().strip()
        
        # 1. Detect Intent
        intent = "UNKNOWN"
        for i, pattern in self._intents_patterns.items():
            if re.search(pattern, text):
                intent = i
                break

        # 2. Extract Spectrum (Ψ-9 / Ω-25)
        # We simulate extraction based on keywords and punctuation
        urgency = 0.5
        if re.search(r"(!|agora|urgente|imediato|ja)", text):
            urgency = 0.9
        
        impact = 0.5
        if re.search(r"(global|todos|full|total|risco maximo)", text):
            impact = 0.8
        
        strategic = 0.5
        if re.search(r"(longo prazo|estrat|architect|plan)", text):
            strategic = 0.7

        spectrum = {
            "literal": 1.0,
            "emotional": 0.2 if urgency < 0.8 else 0.6,
            "strategic": strategic,
            "urgency": urgency,
            "completeness": 0.8,
            "impact": impact,
            "expertise": 0.9
        }

        # 3. Extract Params
        params = {}
        # Parse percentage e.g. "set daily loss 5%"
        pct_match = re.search(r"(\d+(\.\d+)?)%", text)
        if pct_match:
            params["value_pct"] = float(pct_match.group(1))
        
        # Parse numbers e.g. "size 0.5"
        size_match = re.search(r"size\s+([\d.]+)", text)
        if size_match:
            params["size"] = float(size_match.group(1))

        return QROEDispatch(
            intent=intent,
            spectrum=spectrum,
            params=params,
            raw_input=raw_text,
            is_valid=(intent != "UNKNOWN")
        )
