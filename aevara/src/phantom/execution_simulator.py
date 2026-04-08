# @module: aevara.src.phantom.execution_simulator
# @deps: numpy, aevara.src.phantom.scenario_generator
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Motor de replay contrafactual assíncrono com fill modeling,
#           latency injection, e slippage estimation baseado em modelo.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

from aevara.src.phantom.scenario_generator import PhantomScenario


@dataclass(frozen=True, slots=True)
class PhantomOutcome:
    """
    Resultado de simulação contrafactual.
    Imutável por construção. Reprodutível via scenario seed.
    """
    scenario_id: str
    rr_simulated: float                     # Risk-reward simulated
    fill_rate: float                         # [0, 1] probabilidade de fill
    latency_ns: int                          # Latência simulada
    slippage_bps: float                      # Slippage em basis points
    alignment_score: float                   # [0,1] ghost-vs-real proxy
    gradient_vector: Dict[str, float]        # ∂J/∂w_i para shadow DNA


class ExecutionSimulator:
    """
    Simula execução de decisões em cenários contrafactuais.

    Invariantes:
    - Mesmos inputs -> mesmos outputs (determinístico)
    - fill_rate ∈ [0, 1]
    - alignment_score ∈ [0, 1]
    - gradient_vector bounded
    """

    def __init__(self, gradient_clip: float = 1.0, l2_lambda: float = 0.01):
        self._gradient_clip = gradient_clip
        self._l2_lambda = l2_lambda

    async def simulate_execution(
        self,
        scenario: PhantomScenario,
        decision: Dict[str, Any],
        real_rr: Optional[float] = None,
    ) -> PhantomOutcome:
        """
        Simula execução de decisão em cenário contrafactual.

        Args:
            scenario: Cenário gerado
            decision: {side: "long"/"short", size: float, confidence: float}
            real_rr: Realized risk-reward para alinhamento (None se não disponível)

        Returns:
            PhantomOutcome com métricas simuladas
        """
        rng = np.random.default_rng(scenario.seed)
        book = scenario.book_snapshot
        spread = book["spread_bps"]
        imbalance = book["depth_imbalance"]

        # Latency simulation
        latency = self._simulate_latency(scenario.latency_model, rng)

        # Slippage simulation
        slippage = self._simulate_slippage(
            scenario.slippage_model, spread, rng
        )

        # Fill rate (higher imbalance = harder to fill)
        fill_rate = max(0.0, min(1.0, 1.0 - abs(imbalance) * 0.3 - spread * 0.005))

        # Simulated risk-reward
        decision_size = decision.get("size", 1.0)
        confidence = decision.get("confidence", 0.5)
        side = decision.get("side", "long")

        # RR based on regime, spread, slippage
        rr_base = 1.0 if side == "long" else -0.5
        regime_mod = {"trending_up": 0.5, "trending_down": -0.3,
                      "choppy": -0.1, "crisis": -0.8}
        rr_mod = regime_mod.get(scenario.regime_tag, 0.0)
        rr_simulated = rr_base * confidence + rr_mod - slippage * 0.01

        # Alignment with reality
        alignment = self._compute_alignment(rr_simulated, real_rr, rng)

        # Gradient estimation
        gradient = self._estimate_gradient(rr_simulated, decision, rng)

        return PhantomOutcome(
            scenario_id=scenario.scenario_id,
            rr_simulated=float(rr_simulated),
            fill_rate=float(fill_rate),
            latency_ns=int(latency),
            slippage_bps=float(slippage),
            alignment_score=float(alignment),
            gradient_vector=gradient,
        )

    def _simulate_latency(self, model: str, rng: np.random.Generator) -> float:
        if model == "gamma":
            return max(10_000, float(rng.gamma(shape=2.0, scale=5000.0)))
        elif model == "normal":
            return max(10_000, float(rng.normal(50_000, 10_000)))
        else:  # empirical
            return max(10_000, float(rng.exponential(30_000)))

    def _simulate_slippage(self, model: str, spread: float, rng: np.random.Generator) -> float:
        """Slippage em basis points."""
        if model == "power_law":
            # Fat tails: occasional large slippage
            return max(0.0, float(rng.pareto(2.0) * spread * 0.5))
        elif model == "linear":
            return max(0.0, spread * 0.3 * rng.random())
        else:  # empirical
            return max(0.0, float(rng.exponential(spread * 0.2)))

    def _compute_alignment(
        self, simulated_rr: float, real_rr: Optional[float], rng: np.random.Generator
    ) -> float:
        if real_rr is None:
            return 0.5  # Neutral when no reality anchor
        diff = abs(simulated_rr - real_rr)
        # Exponential decay of alignment with difference
        score = np.exp(-diff * 2.0)
        return float(np.clip(score, 0.0, 1.0))

    def _estimate_gradient(
        self, rr: float, decision: Dict[str, Any], rng: np.random.Generator
    ) -> Dict[str, float]:
        """
        Estima ∂J/∂w_i para shadow weights.
        Gradient: positive if RR good, negative if bad.
        Clipped e regularizado.
        """
        base_grad = rr * 0.1  # Scale gradient
        noise = rng.normal(0, 0.01)

        # Simple gradient for common weight keys
        gradient = {}
        for key in ["regime_weight", "volatility_weight", "momentum_weight"]:
            g = base_grad + noise
            # L2 regularization
            g = g - self._l2_lambda * g
            # Clip
            g = float(np.clip(g, -self._gradient_clip, self._gradient_clip))
            gradient[key] = g

        return gradient
