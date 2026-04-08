# @module: aevara.src.phantom.scenario_generator
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Geração estocástica de cenários contrafactuais para book depth,
#           latência, slippage e regime. Determinístico via seed.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

import numpy as np


@dataclass(frozen=True, slots=True)
class PhantomScenario:
    """
    Cenário contrafactual imutável.
    Cada campo é deterministicamente reprodutível via seed.
    """
    scenario_id: str
    regime_tag: str                          # "trending_up", "trending_down", "choppy", "crisis"
    book_snapshot: Dict[str, float]           # {spread_bps, depth_imbalance, mid_price}
    latency_model: str                        # "gamma", "normal", "empirical"
    slippage_model: str                       # "power_law", "linear", "empirical"
    seed: int
    timestamp_ns: int


class ScenarioGenerator:
    """
    Gera cenários estocásticos para PhantomEngine.

    Invariantes:
    - Mesmo seed -> mesmo cenário (reprodutível)
    - Parâmetros bounded (não gera absurdos)
    - Memory: zero estado interno (stateless)
    """

    REGIME_TAGS = ("trending_up", "trending_down", "choppy", "crisis")
    LATENCY_MODELS = ("gamma", "normal", "empirical")
    SLIPPAGE_MODELS = ("power_law", "linear", "empirical")

    def __init__(self, default_seed: int = 42):
        self._default_seed = default_seed

    def generate(
        self,
        scenario_id: str,
        regime_tag: Optional[str] = None,
        latency_model: Optional[str] = None,
        slippage_model: Optional[str] = None,
        seed: Optional[int] = None,
        context: Optional[Dict[str, float]] = None,
    ) -> PhantomScenario:
        """
        Gera um cenário contrafactual.

        Args:
            scenario_id: ID único
            regime_tag: Override de regime (default: aleatório)
            latency_model: Modelo de latência
            slippage_model: Modelo de slippage
            seed: Seed para reprodutibilidade
            context: Contexto de mercado opcional

        Returns:
            PhantomScenario gerado
        """
        rng_seed = seed if seed is not None else self._default_seed
        rng = np.random.default_rng(rng_seed)

        regime = regime_tag or rng.choice(self.REGIME_TAGS)
        lat_model = latency_model or rng.choice(self.LATENCY_MODELS)
        slip_model = slippage_model or rng.choice(self.SLIPPAGE_MODELS)

        # Book snapshot gerado estocasticamente
        ctx = context or {}
        base_spread = ctx.get("spread_bps", rng.uniform(1.0, 20.0))
        imbalance = ctx.get("depth_imbalance", rng.uniform(-1.0, 1.0))
        mid = ctx.get("mid_price", rng.uniform(30000.0, 70000.0))

        # Regime modifiers
        if regime == "crisis":
            base_spread = base_spread * rng.uniform(3.0, 10.0)
            imbalance = np.clip(imbalance * rng.uniform(1.5, 3.0), -1.0, 1.0)
        elif regime.startswith("trending"):
            base_spread = base_spread * rng.uniform(0.5, 1.5)

        book = {
            "spread_bps": float(base_spread),
            "depth_imbalance": float(imbalance),
            "mid_price": float(mid),
        }

        return PhantomScenario(
            scenario_id=scenario_id,
            regime_tag=regime,
            book_snapshot=book,
            latency_model=lat_model,
            slippage_model=slip_model,
            seed=rng_seed,
            timestamp_ns=time.time_ns(),
        )

    def generate_batch(
        self,
        n: int,
        seed_start: int = 0,
        **kwargs,
    ) -> list[PhantomScenario]:
        """Gera lote de cenários. Cada um com seed diferente."""
        scenarios = []
        for i in range(n):
            scenarios.append(self.generate(
                scenario_id=f"phantom_{i:04d}",
                seed=seed_start + i,
                **kwargs,
            ))
        return scenarios
