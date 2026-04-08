# @module: aevara.src.agents.regime.detector
# @deps: aevara.src.agents.base, aevara.src.utils.math
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Detector de regime baseado em HMM simplificado + estatisticas
#           de volatilidade rolling. Classifica mercado em TRENDING,
#           CHOPPY ou CRISIS para ajuste de penalidade na fusão de coerencia.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from aevara.src.agents.base import AgentSignal, BaseAgent
from aevara.src.utils.math import clip, safe_div


class RegimeType(str, Enum):
    TRENDING = "trending"
    CHOPPY = "choppy"
    CRISIS = "crisis"


@dataclass(frozen=True, slots=True)
class RegimeResult:
    """Resultado de classificacao de regime."""
    regime: RegimeType
    confidence: float       # [0, 1]
    volatility: float       # Volatilidade rolling
    trend_strength: float   # [-1, 1] negativo=bearish, positivo=bullish


class RegimeDetector(BaseAgent):
    """
    Detector de regime usando medias rolling e volatilidade.
    MVP: nao usa HMM completo, usa estatisticas de janela.

    Invariantes:
    - min_window >= 10
    - volatility_threshold > 0
    """

    agent_id = "regime"

    def __init__(
        self,
        short_window: int = 10,
        long_window: int = 50,
        volatility_threshold: float = 0.02,
        crisis_threshold: float = 0.05,
    ):
        assert short_window >= 5, "short_window must be >= 5"
        assert long_window > short_window, "long_window must be > short_window"
        assert volatility_threshold > 0, "volatility_threshold must be positive"

        self._short_window = short_window
        self._long_window = long_window
        self._vol_threshold = volatility_threshold
        self._crisis_threshold = crisis_threshold
        self._returns: List[float] = []
        self._prices: List[float] = []

    def update(self, price: float) -> None:
        """Adiciona preco ao historico e calcula retorno."""
        if self._prices:
            ret = (price - self._prices[-1]) / self._prices[-1]
            self._returns.append(ret)
        self._prices.append(price)

        # Prune old returns to memory bounds
        if len(self._returns) > self._long_window * 2:
            self._returns = self._returns[-self._long_window:]

    def classify(self) -> RegimeResult:
        """Classifica o regime atual baseado em volatilidade e tendencia."""
        if len(self._returns) < self._short_window:
            return RegimeResult(
                regime=RegimeType.CHOPPY,
                confidence=0.3,
                volatility=0.0,
                trend_strength=0.0,
            )

        returns = self._returns[-self._long_window:]
        short_returns = returns[-self._short_window:]

        # Volatility (std of returns)
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5

        # Trend strength (mean of short-term returns / volatility)
        short_mean = sum(short_returns) / len(short_returns)
        trend = clip(safe_div(short_mean, volatility), -1.0, 1.0)

        # Classification
        if volatility > self._crisis_threshold:
            regime = RegimeType.CRISIS
        elif volatility > self._vol_threshold or abs(trend) < 0.3:
            regime = RegimeType.CHOPPY
        else:
            regime = RegimeType.TRENDING

        confidence = min(1.0, len(returns) / self._long_window)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            volatility=volatility,
            trend_strength=trend,
        )

    def get_signal(self, features: Dict[str, float]) -> AgentSignal:
        """
        Produz sinal de regime em log-odds.
        Log-odds positivo se trending bullish, negativo se trending bearish.
        Proximo de zero se choppy ou crisis.
        """
        result = self.classify()

        if result.regime == RegimeType.TRENDING:
            logodds = result.trend_strength * 2.0  # [-2, +2]
        elif result.regime == RegimeType.CRISIS:
            logodds = -1.0  # Sinal de defensivo
        else:
            logodds = 0.0  # Neutral em choppy

        logodds = self._clip_logodds(logodds)

        return AgentSignal(
            agent_id=self.agent_id,
            logodds=logodds,
            confidence=self._confidence_from_logodds(logodds),
            metadata={"regime": result.regime.value, "volatility": result.volatility},
        )
