# @module: aevara.src.risk.position_sizing
# @deps: math, dataclasses
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Position sizing com fractional Kelly, volatility targeting,
#           CVaR floor e capping dinamico integrado ao RiskEngine.
#           Kelly fracionario evita blowup em caudas pesadas.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True, slots=True)
class SizingConfig:
    kelly_fraction: float = 0.25         # Fractional Kelly (0.25 = conservative)
    max_leverage: float = 1.0            # Alavancagem maxima
    cvar_floor_pct: float = 2.0          # CVaR maximo (% equity)
    min_position_pct: float = 0.5        # Posicao minima (evita dust trades)
    max_position_pct: float = 15.0       # Posicao maxima (% equity)
    vol_target_pct: float = 15.0         # Volatilidade alvo do portfolio
    return_per_trade_pct: float = 0.1    # Retorno esperado por trade (%)


@dataclass(frozen=True, slots=True)
class PositionSize:
    notional_pct: float      # Tamanho da posicao (% equity)
    kelly_raw: float         # Kelly puro antes de qualquer ajuste
    kelly_adjusted: float    # Kelly apos fractional e vol targeting
    risk_cap_applied: float  # Cap do RiskEngine (0-1)
    final_notional: float    # Notional final apos todos os caps
    is_dust: bool            # Tamanho abaixo do minimo viavel


class PositionSizer:
    """
    Calculo de position sizing com fractional Kelly + volatility targeting.

    Invariantes:
    - Kelly raw: K = p/a - q/b (padrao) -> bound em [0, max_leverage]
    - Kelly adjusted: K * kelly_fraction * vol_target / current_vol
    - CVaR floor: position nunca causa perda > cvar_floor_pct em 1 trade
    - Min position: dust trades sao filtrados (notional < min_position_pct)
    - Risk cap: multiplica notional pelo cap do RiskEngine
    - Todos os outputs em [0, max_position_pct]
    """

    def __init__(self, config: Optional[SizingConfig] = None):
        self._config = config or SizingConfig()

    @staticmethod
    def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calcula Kelly fraction puro: K = (b*p - q) / b
        onde b = avg_win/avg_loss, p = win_rate, q = 1-p
        Retorna valor em [0, 1]. Zero se edge nao positivo.
        """
        if avg_loss <= 0 or avg_win <= 0:
            return 0.0
        if win_rate <= 0 or win_rate >= 1:
            return 0.0

        p = win_rate
        q = 1.0 - p
        b = avg_win / avg_loss

        # K = (b*p - q) / b = p - q/b
        kelly = p - q / b

        return max(0.0, kelly)

    def _vol_adjusted_kelly(self, kelly_raw: float, current_vol_pct: float) -> float:
        """Ajusta Kelly por volatilidade: Kelly * vol_target / vol_current."""
        if current_vol_pct <= 0:
            return kelly_raw
        vol_scale = self._config.vol_target_pct / current_vol_pct
        return kelly_raw * vol_scale

    def _cvar_bounded_size(self, notional_pct: float) -> float:
        """
        Limita tamanho via CVaR floor.
        Pior caso estimado: notional * return_per_trade * 3 (3-sigma conservative).
        Se pior caso > cvar_floor_pct, reduz notional.
        """
        worst_case = notional_pct * self._config.return_per_trade_pct * 3.0
        if worst_case > self._config.cvar_floor_pct:
            return self._config.cvar_floor_pct / (self._config.return_per_trade_pct * 3.0)
        return notional_pct

    def calculate_position(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        current_vol_pct: Optional[float] = None,
        risk_cap: float = 1.0,
    ) -> PositionSize:
        """
        Calcula tamanho otimo da posicao.

        Args:
            win_rate: taxa de acerto historica (0-1)
            avg_win_pct: ganho medio quando acerta (% notional)
            avg_loss_pct: perda media quando erra (% notional)
            current_vol_pct: volatilidade atual do mercado
            risk_cap: cap do RiskEngine (0-1)

        Returns:
            PositionSize com todos os estagios do calculo
        """
        # Stage 1: Kelly raw
        kelly_raw = self.kelly_criterion(win_rate, avg_win_pct, avg_loss_pct)

        # Stage 2: Fractional Kelly
        kelly_fractional = kelly_raw * self._config.kelly_fraction

        # Stage 3: Volatility-adjusted Kelly
        vol = current_vol_pct if current_vol_pct is not None else self._config.vol_target_pct
        kelly_adjusted = self._vol_adjusted_kelly(kelly_fractional, vol)

        # Stage 4: Leverage cap
        kelly_adjusted = min(kelly_adjusted, self._config.max_leverage)

        # Stage 5: Convert para % equity (Kelly ja e fracao de capital)
        notional_pct = kelly_adjusted * 100.0

        # Stage 6: CVaR floor
        notional_pct = self._cvar_bounded_size(notional_pct)

        # Stage 7: Risk cap
        notional_pct *= risk_cap

        # Stage 8: Position bounds
        notional_pct = max(0.0, min(notional_pct, self._config.max_position_pct))

        # Stage 9: Dust detection
        is_dust = notional_pct < self._config.min_position_pct
        if is_dust:
            notional_pct = 0.0

        return PositionSize(
            notional_pct=notional_pct,
            kelly_raw=kelly_raw,
            kelly_adjusted=kelly_adjusted,
            risk_cap_applied=risk_cap,
            final_notional=notional_pct,
            is_dust=is_dust,
        )

    def get_config(self) -> Dict[str, Any]:
        """Retorna configuracao atual."""
        return {
            "kelly_fraction": self._config.kelly_fraction,
            "max_leverage": self._config.max_leverage,
            "cvar_floor_pct": self._config.cvar_floor_pct,
            "min_position_pct": self._config.min_position_pct,
            "max_position_pct": self._config.max_position_pct,
            "vol_target_pct": self._config.vol_target_pct,
        }
