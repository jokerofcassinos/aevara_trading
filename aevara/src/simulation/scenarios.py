# @module: aevara.src.simulation.scenarios
# @deps: typing, numpy, dataclasses
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Scenario generation for cognitive stress-testing (Ω-45). Shock injection logic.

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass(frozen=True, slots=True)
class ScenarioParameters:
    drift: float
    volatility: float
    jump_intensity: float = 0.05 # Probabilidade de choque por passo
    shock_magnitude: float = -0.05 # -5% crash magnitude

class ScenarioGenerator:
    """
    Gerador de Cenários (Ω-45).
    Gera caminhos de stress usando Monte Carlo com injeção de choques nas caudas.
    """
    def generate_stress_paths(self, 
                              n_paths: int = 100, 
                              horizon: int = 20, 
                              params: Optional[ScenarioParameters] = None) -> np.ndarray:
        """
        Gera matriz de caminhos (n_paths, horizon) com Black-Scholes + Choques de Cauda.
        """
        p = params or ScenarioParameters(drift=0.0001, volatility=0.01)
        
        # Base: Retornos Gaussianos
        paths = np.random.normal(p.drift, p.volatility, (n_paths, horizon))
        
        # Injeção de Choques
        if p.jump_intensity > 0:
            jumps = (np.random.rand(n_paths, horizon) < p.jump_intensity).astype(float)
            paths += jumps * p.shock_magnitude
            
        return paths

    async def generate(self, params: ScenarioParameters) -> List[float]:
        """Gera um único caminho asíncrono para validação rápida."""
        path = self.generate_stress_paths(1, 20, params)[0]
        return path.tolist()
