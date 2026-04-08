# @module: aevara.src.cognitive.substrate
# @deps: typing, numpy, scipy
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Cognitive substrate for belief updating and uncertainty quantification (Ψ-1).

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True, slots=True)
class BeliefState:
    mean: float
    variance: float
    entropy: float

class CognitiveSubstrate:
    """
    Substrato Cognitivo (Ψ-1).
    Gerencia a atualização Bayesiana de crenças sobre regimes de mercado e estados internos.
    """
    def __init__(self, initial_prior: float = 0.5, initial_var: float = 0.25):
        self.current_mean = initial_prior
        self.current_var = initial_var

    def update_belief_state(self, evidence: float, likelihood_var: float = 0.1) -> BeliefState:
        """
        Bayesian Update: Fusão do Prior com a nova Evidência Gaussiana.
        Novas crenças = (Prior/Var_p + Evidence/Var_e) / (1/Var_p + 1/Var_e)
        """
        prior_mean = self.current_mean
        prior_var = self.current_var
        
        # Kalman-like update para um escalar
        new_var = 1.0 / (1.0/prior_var + 1.0/likelihood_var)
        new_mean = new_var * (prior_mean/prior_var + evidence/likelihood_var)
        
        self.current_mean = float(new_mean)
        self.current_var = float(new_var)
        
        # Entropia de uma Gaussiana: 0.5 * log(2*pi*e*var)
        entropy = 0.5 * np.log(2 * np.pi * np.e * new_var)
        
        return BeliefState(mean=self.current_mean, variance=self.current_var, entropy=float(entropy))

    def quantify_uncertainty(self) -> float:
        """Retorna a incerteza atual baseada na variância da crença."""
        return float(self.current_var)

    async def process(self, input_evidence: Optional[float] = None) -> BeliefState:
        """Interface assíncrona para o loop cognitivo."""
        if input_evidence is not None:
            return self.update_belief_state(input_evidence)
        return BeliefState(self.current_mean, self.current_var, 0.0)
