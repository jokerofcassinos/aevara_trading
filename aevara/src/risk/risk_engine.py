# @module: aevara.src.risk.risk_engine
# @deps: math, time, dataclasses
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Risk engine com vetos dinamicos, drawdown circuit breaker,
#           exposure caps e position cap calculation baseado em coerencia,
#           volatilidade e regime. Position cap multiplica sizing, nao vetos isolados.

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class VetoReason(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    EXPOSURE_CAP = "EXPOSURE_CAP"
    REGIME_HOSTILE = "REGIME_HOSTILE"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_drawdown_pct: float = 5.0       # Hard limit (% de equity)
    soft_drawdown_pct: float = 3.0      # Soft limit (reduz sizing)
    max_position_pct: float = 10.0      # Max % equity por posicao
    max_gross_exposure_pct: float = 150.0
    max_net_exposure_pct: float = 100.0
    vol_target_pct: float = 15.0        # Volatilidade alvo do portfolio
    vol_window: int = 100               # Janela para vol rolling
    max_consecutive_losses: int = 5     # Circuit breaker trigger


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    position_cap: float       # 0.0 - 1.0 (multiplicador de sizing)
    vetos: Tuple[VetoReason, ...]
    is_blocked: bool
    reason: str = ""


class RiskEngine:
    """
    Motor de risco com vetos dinamicos e drawdown circuit breaker.

    Invariantes:
    - position_cap em [0.0, 1.0] sempre
    - Veto total (cap=0, is_blocked=True) quando qualquer hard limit violado
    - Drawdown circuit breaker: soft limit reduz cap, hard para
    - Consecutive losses trigger circuit breaker automaticamente
    - Memory bounded: rolling vol window truncado
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self._config = config or RiskConfig()
        self._peak_equity = 1.0
        self._current_equity = 1.0
        self._consecutive_losses = 0
        self._is_circuit_open = False
        self._vol_history: List[float] = []

    # === PEAK / DRAWDOWN ===
    def update_equity(self, equity: float) -> None:
        """Atualiza equity corrente. Mantem peak e detecta drawdown."""
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

    @property
    def current_drawdown_pct(self) -> float:
        """Drawdown atual como % do peak."""
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._current_equity) / self._peak_equity * 100

    # === VOLATILITY TRACKING ===
    def record_vol(self, vol_pct: float) -> None:
        """Registra volatilidade para tracking. Window truncado."""
        self._vol_history.append(vol_pct)
        max_len = self._config.vol_window * 2
        if len(self._vol_history) > max_len:
            self._vol_history = self._vol_history[-self._config.vol_window:]

    @property
    def current_vol_pct(self) -> float:
        """Retorna vol media rolling."""
        if not self._vol_history:
            return 0.0
        return sum(self._vol_history[-self._config.vol_window:]) / len(self._vol_history[-self._config.vol_window:])

    # === CIRCUIT BREAKER ===
    def record_loss(self) -> None:
        """Registra perda. Abre circuito se consecutivas > threshold."""
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._config.max_consecutive_losses:
            self._is_circuit_open = True

    def record_gain(self) -> None:
        """Registra ganho. Reseta contador de perdas."""
        self._consecutive_losses = 0
        self._is_circuit_open = False

    @property
    def is_circuit_open(self) -> bool:
        """Circuito aberto por perdas consecutivas."""
        return self._is_circuit_open

    # === ASSESSMENT ===
    def assess_risk(
        self,
        signal_confidence: float = 0.5,   # 0.0 - 1.0
        regime_hostile: bool = False,
        proposed_notional_pct: float = 0.0,  # % of equity proposed
    ) -> RiskAssessment:
        """
        Avalia risco para trade proposto.

        Args:
            signal_confidence: confianca do sinal (0-1)
            regime_hostile: regime adverso detectado
            proposed_notional_pct: tamanho proposto (% equity)

        Returns:
            RiskAssessment com position_cap e vetos
        """
        vetos: List[VetoReason] = []
        cap = 1.0

        # Hard veto: circuit breaker
        if self._is_circuit_open:
            vetos.append(VetoReason.CIRCUIT_BREAKER)
            cap = 0.0
            return RiskAssessment(
                position_cap=0.0,
                vetos=tuple(vetos),
                is_blocked=True,
                reason="Circuit breaker open (consecutive losses)",
            )

        # Hard veto: drawdown limit
        dd = self.current_drawdown_pct
        if dd >= self._config.max_drawdown_pct:
            vetos.append(VetoReason.DRAWDOWN_LIMIT)
            cap = 0.0
            return RiskAssessment(
                position_cap=0.0,
                vetos=tuple(vetos),
                is_blocked=True,
                reason=f"Drawdown {dd:.2f}% exceeds max {self._config.max_drawdown_pct}%",
            )

        # Soft reduction: between soft and hard drawdown
        if dd >= self._config.soft_drawdown_pct:
            reduction = (dd - self._config.soft_drawdown_pct) / (self._config.max_drawdown_pct - self._config.soft_drawdown_pct)
            cap = max(0.0, 1.0 - reduction * 0.8)  # Reduz ate 80% no maximo

        # Hard veto: regime hostil + confianca baixa
        if regime_hostile and signal_confidence < 0.3:
            vetos.append(VetoReason.REGIME_HOSTILE)
            cap = 0.0
            return RiskAssessment(
                position_cap=0.0,
                vetos=tuple(vetos),
                is_blocked=True,
                reason="Hostile regime with low confidence signal",
            )

        # Soft reduction: baixa confianca
        if signal_confidence < 0.3:
            vetos.append(VetoReason.LOW_CONFIDENCE)
            cap *= max(0.0, signal_confidence / 0.3)

        # Soft reduction: alta volatilidade (2x target)
        vol = self.current_vol_pct
        vol_cap = self._config.vol_target_pct * 2.0
        if vol > vol_cap:
            vetos.append(VetoReason.HIGH_VOLATILITY)
            vol_reduction = min(1.0, vol / (vol_cap * 2.0))
            cap *= max(0.0, 1.0 - vol_reduction * 0.7)

        # Exposure cap check
        if proposed_notional_pct > self._max_position_pct:
            vetos.append(VetoReason.EXPOSURE_CAP)
            cap = min(cap, self._max_position_pct / proposed_notional_pct) if proposed_notional_pct > 0 else 0.0

        cap = max(0.0, min(1.0, cap))
        is_blocked = cap <= 0.0

        return RiskAssessment(
            position_cap=cap,
            vetos=tuple(vetos),
            is_blocked=is_blocked,
            reason=", ".join(v.value for v in vetos) if vetos else "",
        )

    @property
    def _max_position_pct(self) -> float:
        return self._config.max_position_pct

    @property
    def max_position_notional(self) -> float:
        """Retorna notional maximo por posicao em % equity."""
        return self._config.max_position_pct

    @property
    def max_gross_exposure(self) -> float:
        return self._config.max_gross_exposure_pct

    @property
    def max_net_exposure(self) -> float:
        return self._config.max_net_exposure_pct

    # === STATE ===
    def reset(self) -> None:
        """Reseta estado (drawdown, circuito, etc)."""
        self._peak_equity = self._current_equity
        self._consecutive_losses = 0
        self._is_circuit_open = False

    def get_state(self) -> Dict[str, Any]:
        """Retorna snapshot do estado de risco."""
        return {
            "peak_equity": self._peak_equity,
            "current_equity": self._current_equity,
            "drawdown_pct": self.current_drawdown_pct,
            "consecutive_losses": self._consecutive_losses,
            "is_circuit_open": self._is_circuit_open,
            "current_vol_pct": self.current_vol_pct,
            "vol_samples": len(self._vol_history),
        }
