# @module: aevara.src.risk.exposure_tracker
# @deps: dataclasses, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Exposure tracker com notional tracking por posicao, concentration
#           limits, net/gross ratio e validacao de limites de exposicao total.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class PositionExposure:
    symbol: str
    side: PositionSide
    notional_pct: float     # % de equity
    entry_price: float
    entry_ts: float


@dataclass(frozen=True, slots=True)
class ExposureSnapshot:
    gross_exposure_pct: float    # Soma absoluta de todas as posicoes
    net_exposure_pct: float      # Longs - Shorts
    long_exposure_pct: float     # Total longs
    short_exposure_pct: float    # Total shorts
    position_count: int
    largest_position_pct: float  # Maior posicao individual
    concentration_ratio: float   # largest / gross (1 = single position)
    is_within_limits: bool
    violations: Tuple[str, ...]


class ExposureTracker:
    """
    Rastreamento de exposicao em tempo real.

    Invariantes:
    - Gross = soma(|notional|) de todas as posicoes
    - Net = soma(Long) - soma(Short)
    - Concentration bounded: largest_position / gross <= 1.0
    - Violations detectadas antes de adicionar nova posicao
    - Memory bounded: max 50 posicoes
    """

    def __init__(
        self,
        max_positions: int = 20,
        max_gross_pct: float = 150.0,
        max_net_pct: float = 100.0,
        max_single_pct: float = 15.0,
    ):
        assert max_positions > 0
        assert max_gross_pct > 0
        assert max_net_pct >= 0
        assert max_single_pct > 0
        self._positions: Dict[str, PositionExposure] = {}
        self._max_positions = max_positions
        self._max_gross_pct = max_gross_pct
        self._max_net_pct = max_net_pct
        self._max_single_pct = max_single_pct

    def _long_total(self) -> float:
        return sum(
            p.notional_pct for p in self._positions.values()
            if p.side == PositionSide.LONG
        )

    def _short_total(self) -> float:
        return sum(
            p.notional_pct for p in self._positions.values()
            if p.side == PositionSide.SHORT
        )

    def _largest_position(self) -> float:
        if not self._positions:
            return 0.0
        return max(p.notional_pct for p in self._positions.values())

    def add_position(
        self,
        symbol: str,
        side: PositionSide,
        notional_pct: float,
        entry_price: float,
        entry_ts: float,
    ) -> Tuple[bool, str]:
        """
        Adiciona posicao. Valida limites antes de adicionar.
        Returns (success, reason).
        """
        if notional_pct <= 0:
            return (False, "Notional must be positive")

        if symbol in self._positions:
            return (False, f"Position {symbol} already exists")

        # Check max positions
        if len(self._positions) >= self._max_positions:
            return (False, f"Max positions limit ({self._max_positions}) reached")

        # Check single position limit
        if notional_pct > self._max_single_pct:
            return (False, f"Position size {notional_pct:.1f}% exceeds max {self._max_single_pct}%")

        # Check gross exposure
        projected_gross = self._gross_after(notional_pct)
        if projected_gross > self._max_gross_pct:
            return (False, f"Gross exposure {projected_gross:.1f}% would exceed limit {self._max_gross_pct}%")

        # Check net exposure
        if side == PositionSide.LONG:
            projected_net = self._long_total() + notional_pct - self._short_total()
        else:
            projected_net = self._long_total() - (self._short_total() + notional_pct)
        if abs(projected_net) > self._max_net_pct:
            return (False, f"Net exposure would exceed limit {self._max_net_pct}%")

        self._positions[symbol] = PositionExposure(
            symbol=symbol,
            side=side,
            notional_pct=notional_pct,
            entry_price=entry_price,
            entry_ts=entry_ts,
        )
        return (True, "")

    def _gross_after(self, additional_notional: float) -> float:
        current_gross = sum(p.notional_pct for p in self._positions.values())
        return current_gross + additional_notional

    def remove_position(self, symbol: str) -> bool:
        """Remove posicao por simbolo."""
        if symbol in self._positions:
            del self._positions[symbol]
            return True
        return False

    def update_position(self, symbol: str, notional_pct: float) -> Tuple[bool, str]:
        """Atualiza notional de posicao existente."""
        if symbol not in self._positions:
            return (False, f"Position {symbol} not found")

        if notional_pct <= 0:
            return (False, "Notional must be positive")

        if notional_pct > self._max_single_pct:
            return (False, f"Position size {notional_pct:.1f}% exceeds max {self._max_single_pct}%")

        old = self._positions[symbol]
        delta = notional_pct - old.notional_pct

        projected_gross = sum(p.notional_pct for p in self._positions.values()) + delta
        if projected_gross > self._max_gross_pct:
            return (False, f"Update would exceed gross limit")

        self._positions[symbol] = PositionExposure(
            symbol=old.symbol,
            side=old.side,
            notional_pct=notional_pct,
            entry_price=old.entry_price,
            entry_ts=old.entry_ts,
        )
        return (True, "")

    def get_snapshot(self) -> ExposureSnapshot:
        """Retorna snapshot completo da exposicao."""
        long_total = self._long_total()
        short_total = self._short_total()
        gross = long_total + short_total
        net = long_total - short_total
        largest = self._largest_position()

        violations: List[str] = []
        if gross > self._max_gross_pct:
            violations.append(f"Gross {gross:.1f}% > {self._max_gross_pct}%")
        if abs(net) > self._max_net_pct:
            violations.append(f"Net {net:.1f}% > {self._max_net_pct}%")
        if largest > self._max_single_pct:
            violations.append(f"Largest {largest:.1f}% > {self._max_single_pct}%")

        return ExposureSnapshot(
            gross_exposure_pct=gross,
            net_exposure_pct=net,
            long_exposure_pct=long_total,
            short_exposure_pct=short_total,
            position_count=len(self._positions),
            largest_position_pct=largest,
            concentration_ratio=largest / gross if gross > 0 else 0.0,
            is_within_limits=len(violations) == 0,
            violations=tuple(violations),
        )

    def get_position(self, symbol: str) -> Optional[PositionExposure]:
        """Retorna posicao por simbolo."""
        return self._positions.get(symbol)

    def position_count(self) -> int:
        return len(self._positions)

    def clear(self) -> None:
        self._positions.clear()

    def get_all_positions(self) -> Dict[str, PositionExposure]:
        return dict(self._positions)
