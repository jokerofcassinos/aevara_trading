# @module: aevara.src.infra.stress.market_adversary
# @deps: random, math, time, dataclasses, numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Adversarial market scenario generation: flash crash, spoofing,
#           latency injection, exchange downtime replay, fat-tail sequences.
#           Gera sequencias adversariais realistas para stress-testing.

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class MarketShockType(str, Enum):
    FLASH_CRASH = "FLASH_CRASH"
    SPOOFING = "SPOOFING"
    LATENCY_SPIKE = "LATENCY_SPIKE"
    EXCHANGE_DOWNTIME = "EXCHANGE_DOWNTIME"
    GAPPING = "GAPPING"
    VOL_CLUSTERING = "VOL_CLUSTERING"


@dataclass(frozen=True, slots=True)
class AdversarialConfig:
    """Configuracao para cenarios adversariais."""
    flash_crash_drop_pct: float = 10.0       # Drop maximo em flash crash
    flash_crash_duration_s: float = 120.0     # Duracao em segundos
    spoof_cancel_rate: float = 0.75           # % de ordens canceladas (spoofing)
    latency_spike_ms: int = 5000              # Pico de latencia
    downtime_duration_s: float = 300.0        # Duracao de downtime
    gap_size_pct: float = 5.0                 # Tamanho de gap entre candles
    vol_multiplier: float = 5.0               # Multiplicador de volatilidade
    fat_tail_alpha: float = 2.5               # Pareto tail index (2-4 typical)


@dataclass(frozen=True, slots=True)
class AdversarialEvent:
    """Evento adversarial gerado."""
    shock_type: MarketShockType
    ts: float
    severity: float          # 0.0 - 1.0
    duration_s: float
    parameters: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class StressResult:
    """Resultado de teste de stress."""
    total_events: int
    max_loss_pct: float
    recovery_time_s: float
    strategy_survived: bool
    metrics: Dict[str, Any]


class MarketAdversary:
    """
    Gera cenarios adversariais para stress-testing de estrategias.

    Invariantes:
    - Reprodutibilidade via seed deterministico
    - Severidade calibrada em escala realista
    - Composicao de multi-choques possivel
    - Bounded: max N eventos por sequencia
    """

    def __init__(self, config: Optional[AdversarialConfig] = None, seed: Optional[int] = None):
        self._config = config or AdversarialConfig()
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)

    def generate_flash_crash(self, base_price: float, base_vol: float) -> List[AdversarialEvent]:
        """
        Flash crash: queda rapida e profunda com recovery parcial.
        Drop exponencial + recovery logaritmica.
        """
        cfg = self._config
        drop_pct = cfg.flash_crash_drop_pct * self._rng.uniform(0.3, 1.0)
        duration = cfg.flash_crash_duration_s * self._rng.uniform(0.5, 1.5)

        # Phases: crash (fast), bottom (volatile), recovery (slow)
        crash_phase = duration * 0.15
        bottom_phase = duration * 0.25
        recovery_phase = duration * 0.60

        return [
            AdversarialEvent(
                shock_type=MarketShockType.FLASH_CRASH,
                ts=time.time(),
                severity=drop_pct / 100.0,
                duration_s=crash_phase,
                parameters={
                    "base_price": base_price,
                    "drop_pct": drop_pct,
                    "vol_multiplier": cfg.vol_multiplier * 2.0,
                    "phase": "CRASH",
                },
            ),
            AdversarialEvent(
                shock_type=MarketShockType.VOL_CLUSTERING,
                ts=time.time() + crash_phase,
                severity=0.6,
                duration_s=bottom_phase,
                parameters={
                    "base_price": base_price * (1 - drop_pct / 100.0),
                    "vol_multiplier": cfg.vol_multiplier * 3.0,
                    "mean_reversion": 0.0,
                    "phase": "BOTTOM",
                },
            ),
            AdversarialEvent(
                shock_type=MarketShockType.FLASH_CRASH,
                ts=time.time() + crash_phase + bottom_phase,
                severity=0.3,
                duration_s=recovery_phase,
                parameters={
                    "base_price": base_price * (1 - drop_pct / 100.0),
                    "recovery_target": base_price * 0.85,
                    "vol_multiplier": cfg.vol_multiplier * 1.5,
                    "phase": "RECOVERY",
                },
            ),
        ]

    def generate_spoofing(self, symbol: str, direction: str = "SELL") -> List[AdversarialEvent]:
        """
        Spoofing: ordens falsas no book com cancel rate alto.
        Gera padrao de layering com spoof_cancel_rate.
        """
        n_layers = self._rng.randint(3, 8)
        events: List[AdversarialEvent] = []

        for layer in range(n_layers):
            spoof_size = self._rng.uniform(50, 500)  # Contratos falsos
            distance_bps = self._rng.uniform(5, 50)  # Distancia do mid

            events.append(AdversarialEvent(
                shock_type=MarketShockType.SPOOFING,
                ts=time.time() + layer * 0.1,
                severity=self._config.spoof_cancel_rate,
                duration_s=self._rng.uniform(0.5, 3.0),
                parameters={
                    "symbol": symbol,
                    "direction": direction,
                    "layer": layer,
                    "spoof_size": spoof_size,
                    "distance_bps": distance_bps,
                    "cancel_rate": self._config.spoof_cancel_rate,
                },
            ))

        return events

    def generate_latency_spike(self, base_latency_ms: int = 50) -> List[AdversarialEvent]:
        """
        Latency spike: aumento improviso de latencia.
        Distribuicao Gamma com cauda pesada.
        """
        spike_duration = self._rng.uniform(5.0, 30.0)
        peak_latency = self._config.latency_spike_ms

        return [
            AdversarialEvent(
                shock_type=MarketShockType.LATENCY_SPIKE,
                ts=time.time(),
                severity=min(1.0, peak_latency / (base_latency_ms * 100)),
                duration_s=spike_duration,
                parameters={
                    "base_latency_ms": base_latency_ms,
                    "peak_latency_ms": peak_latency,
                    "distribution": "gamma",
                    "gamma_k": 2.0,
                    "gamma_theta": peak_latency / (2.0 * 1000.0),
                },
            )
        ]

    def generate_exchange_downtime(self) -> List[AdversarialEvent]:
        """
        Exchange downtime: exchange fica indisponivel.
        Sem possibilidade de executar ordens ou obter precos.
        """
        return [
            AdversarialEvent(
                shock_type=MarketShockType.EXCHANGE_DOWNTIME,
                ts=time.time(),
                severity=0.8,
                duration_s=self._config.downtime_duration_s,
                parameters={
                    "ws_disconnected": True,
                    "rest_timeouts": 10,
                    "data_gap": True,
                },
            )
        ]

    def generate_fat_tail_returns(self, n_samples: int = 1000) -> np.ndarray:
        """
        Gera retornos com cauda pesada (Pareton).
        P(|r| > x) ~ x^(-alpha), alpha em [2.0, 4.0].
        """
        alpha = self._config.fat_tail_alpha
        # Pareto: X = (U)^(-1/alpha) - 1, U ~ Uniform(0,1)
        u = self._np_rng.uniform(0.01, 1.0, size=n_samples)
        pareto = np.power(u, -1.0 / alpha) - 1.0

        # Mistura com normal para corpo da distribuicao
        normal = self._np_rng.normal(0, 0.01, size=n_samples)
        mixture_weight = 0.15  # 15% cauda pesada

        returns = (1 - mixture_weight) * normal + mixture_weight * pareto * 0.1
        return returns

    def generate_gapping(self, base_price: float) -> List[AdversarialEvent]:
        """
        Price gap: salto descontínuo entre precos (abertura apos weekend, noticias).
       """
        gap_pct = self._config.gap_size_pct * self._rng.uniform(0.5, 2.0)
        direction = self._rng.choice([-1, 1])

        return [
            AdversarialEvent(
                shock_type=MarketShockType.GAPPING,
                ts=time.time(),
                severity=gap_pct / 100.0,
                duration_s=0.0,
                parameters={
                    "base_price": base_price,
                    "gap_price": base_price * (1 + direction * gap_pct / 100.0),
                    "direction": "UP" if direction > 0 else "DOWN",
                    "gap_pct": gap_pct,
                },
            )
        ]

    def apply_latency_to_event(
        self, event: AdversarialEvent, base_latency_ms: int = 50
    ) -> float:
        """
        Calcula latencia efetiva para um evento.
        Gamma distribution com cauda pesada.
        """
        if event.shock_type == MarketShockType.LATENCY_SPIKE:
            peak_ms = event.parameters.get("peak_latency_ms", 5000)
            gamma_k = event.parameters.get("gamma_k", 2.0)
            gamma_theta = event.parameters.get("gamma_theta", 2.5)
            return self._np_rng.gamma(gamma_k, gamma_theta) * 1000.0  # ms
        return self._rng.gauss(base_latency_ms, base_latency_ms * 0.3)

    def generate_multi_shock(
        self, n_shocks: int = 3, base_price: float = 50000.0
    ) -> List[AdversarialEvent]:
        """
        Gera sequencia de multi-choques compostos.
        """
        all_events: List[AdversarialEvent] = []
        shock_types = [
            self.generate_flash_crash,
            self.generate_spoofing,
            self.generate_gapping,
        ]

        for i in range(n_shocks):
            generator = self._rng.choice(shock_types)
            if generator == self.generate_flash_crash:
                events = generator(base_price, 1.0)
            elif generator == self.generate_spoofing:
                direction = self._rng.choice(["BUY", "SELL"])
                events = generator("BTC/USD", direction)
            else:
                events = generator(base_price)

            # Offset temporal
            offset = i * self._rng.uniform(5.0, 30.0)
            all_events.extend(
                AdversarialEvent(
                    shock_type=e.shock_type,
                    ts=e.ts + offset,
                    severity=e.severity,
                    duration_s=e.duration_s,
                    parameters=e.parameters,
                )
                for e in events
            )

        all_events.sort(key=lambda e: e.ts)
        return all_events

    def get_severity_distribution(self, n: int = 1000) -> np.ndarray:
        """
        Distribuicao de severidade dos choques.
        Beta(2,5) concentrada em valores baixos com cauda longa.
        """
        return self._np_rng.beta(2, 5, size=n)
