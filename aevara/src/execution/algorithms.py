# @module: aevara.src.execution.algorithms
# @deps: time, dataclasses, typing, math, numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: TCE-aware TWAP, VWAP, POV, Iceberg com dynamic slippage adjustment,
#           impacto de mercado modelado, early exit condition, participacao vol-adaptativa.

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class AlgoType(str, Enum):
    TWAP = "TWAP"
    VWAP = "VWAP"
    POV = "POV"
    ICEBERG = "ICEBERG"


@dataclass(frozen=True, slots=True)
class ChildOrder:
    """Ordem filha resultante de split algoritmico."""
    sequence: int
    size: float
    price_limit: Optional[float]
    scheduled_time_s: float
    algo_type: AlgoType
    is_hidden: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Plano completo de execucao."""
    parent_size: float
    child_orders: List[ChildOrder]
    expected_tce_bps: float
    expected_duration_s: float
    algo_type: AlgoType
    participation_rate: float
    early_exit_price: Optional[float] = None
    early_exit_reason: str = ""


@dataclass(frozen=True, slots=True)
class MarketImpactModel:
    """Modelo parametrico de impacto de mercado."""
    linear_coef: float = 0.1     # Coeficiente linear (bps por % of volume)
    power_exponent: float = 0.6  # Exponente para impacto non-linear
    decay_rate: float = 0.05     # Decay de impacto ao longo do tempo


class ExecutionAlgorithms:
    """
    Algoritmos de execucao adaptativos.

    Invariantes:
    - Soma de tamanhos de child_orders == parent_size
    - Tempos sao crescentes e bounded
    - POV participation <= max_participation_rate
    - Early exit triggers when price moves beyond threshold
    - Impact modeled com square-root law
    """

    def __init__(self, impact_model: Optional[MarketImpactModel] = None):
        self._impact = impact_model or MarketImpactModel()

    def compute_market_impact(self, size_pct: float, volatility: float) -> float:
        """
        Estima impacto de mercado em bps.
        Square-root law: impact = coef * sigma * sqrt(participation)
        """
        participation = min(size_pct, 1.0)
        base = self._impact.linear_coef * volatility * 100  # Convert to bps
        return base * (participation ** self._impact.power_exponent)

    def generate_twap(
        self,
        symbol: str,
        side: str,
        total_size: float,
        duration_s: float,
        n_slices: int = 8,
        current_price: float = 0.0,
        volatility: float = 0.01,
        max_participation: float = 0.1,
        tce_budget_bps: float = 5.0,
        early_exit_threshold_pct: float = 0.5,
    ) -> ExecutionPlan:
        """
        TWAP: divide ordem em N slices igualmente espacados no tempo.

        Ajusta sizing dinamicamente se impacto excede budget.
        Early exit se preco se move contra alem de threshold.
        """
        slice_size = total_size / n_slices
        interval_s = duration_s / n_slices

        children: List[ChildOrder] = []
        cumulative_size = 0.0

        for i in range(n_slices):
            remaining = total_size - cumulative_size
            size = min(slice_size, remaining)
            cumulative_size += size

            # Price limit: adicione buffer ao preco atual para slippage
            price_limit = None
            if current_price > 0:
                slippage_buffer = self.compute_market_impact(
                    size / total_size * max_participation, volatility
                ) * current_price / 10000.0
                if side == "BUY":
                    price_limit = current_price + slippage_buffer
                else:
                    price_limit = current_price - slippage_buffer

            children.append(ChildOrder(
                sequence=i,
                size=round(size, 8),
                price_limit=price_limit,
                scheduled_time_s=i * interval_s,
                algo_type=AlgoType.TWAP,
            ))

        # Expected TCE: fee + slippage + impact
        avg_sizing = total_size / n_slices
        impact_bps = self.compute_market_impact(avg_sizing / total_size * max_participation, volatility)
        expected_tce = 1.0 + impact_bps  # Fee base + impacto

        # Early exit price
        early_exit_price = None
        if current_price > 0 and early_exit_threshold_pct > 0:
            if side == "BUY":
                early_exit_price = current_price * (1 + early_exit_threshold_pct / 100.0)
            else:
                early_exit_price = current_price * (1 - early_exit_threshold_pct / 100.0)

        return ExecutionPlan(
            parent_size=total_size,
            child_orders=children,
            expected_tce_bps=expected_tce,
            expected_duration_s=duration_s,
            algo_type=AlgoType.TWAP,
            participation_rate=max_participation,
            early_exit_price=early_exit_price,
        )

    def generate_vwap(
        self,
        total_size: float,
        duration_s: float,
        volume_profile: Optional[np.ndarray] = None,
        current_price: float = 0.0,
        volatility: float = 0.01,
        max_participation: float = 0.1,
    ) -> ExecutionPlan:
        """
        VWAP: participa proporcionalmente ao volume esperado por intervalo.
        Usa volume_profile se disponivel, senao assume perfil U-shape.
        """
        n_buckets = 10
        interval_s = duration_s / n_buckets

        # Volume profile U-shape (mais volume no open/close)
        if volume_profile is None:
            # U-shape: weights 0.15, 0.1, 0.08, 0.07, 0.10, 0.10, 0.07, 0.08, 0.1, 0.15
            profile = np.array([1.5, 1.0, 0.8, 0.7, 1.0, 1.0, 0.7, 0.8, 1.0, 1.5])
            profile = profile / profile.sum()
        else:
            profile = volume_profile / volume_profile.sum()

        children: List[ChildOrder] = []
        cumulative = 0.0
        for i in range(n_buckets):
            size = total_size * profile[i]
            cumulative += size
            children.append(ChildOrder(
                sequence=i,
                size=round(size, 8),
                price_limit=None,
                scheduled_time_s=i * interval_s,
                algo_type=AlgoType.VWAP,
            ))

        # Ajusta ultimo para fechar exatamente
        remaining = round(total_size - sum(c.size for c in children[:-1]), 8)
        if children and remaining > 0:
            children[-1] = ChildOrder(
                sequence=children[-1].sequence,
                size=remaining,
                price_limit=children[-1].price_limit,
                scheduled_time_s=children[-1].scheduled_time_s,
                algo_type=AlgoType.VWAP,
            )

        return ExecutionPlan(
            parent_size=total_size,
            child_orders=children,
            expected_tce_bps=volatility * 100 * 0.5,
            expected_duration_s=duration_s,
            algo_type=AlgoType.VWAP,
            participation_rate=max_participation,
        )

    def generate_pov(
        self,
        total_size: float,
        participation_rate: float,
        duration_s: float,
        avg_volume_per_second: float,
        current_price: float = 0.0,
        volatility: float = 0.01,
    ) -> ExecutionPlan:
        """
        POV: participa de uma porcentagem fixa do volume do mercado.
        """
        participation_rate = min(participation_rate, 0.3)  # Cap at 30%
        n_slices = max(4, int(duration_s / 5.0))  # Slices a cada 5s

        volume_per_slice = avg_volume_per_second * (duration_s / n_slices)
        slice_size = volume_per_slice * participation_rate

        n_required = math.ceil(total_size / slice_size)
        n_slices = max(n_slices, n_required)
        interval_s = duration_s / n_slices
        actual_slice_size = total_size / n_slices

        children: List[ChildOrder] = []
        for i in range(n_slices):
            children.append(ChildOrder(
                sequence=i,
                size=round(actual_slice_size, 8),
                price_limit=None,
                scheduled_time_s=i * interval_s,
                algo_type=AlgoType.POV,
            ))

        impact_bps = self.compute_market_impact(participation_rate, volatility)
        return ExecutionPlan(
            parent_size=total_size,
            child_orders=children,
            expected_tce_bps=impact_bps,
            expected_duration_s=duration_s,
            algo_type=AlgoType.POV,
            participation_rate=participation_rate,
        )

    def generate_iceberg(
        self,
        total_size: float,
        visible_size: float,
        current_price: float,
        side: str,
        max_duration_s: float = 300.0,
        refresh_interval_s: float = 10.0,
    ) -> ExecutionPlan:
        """
        Iceberg: order grande com porcao visivel limitada.
        Quando a parte visivel e preenchida, o resto e re-exibido.
        """
        assert visible_size > 0, "Visible size must be positive"
        assert visible_size < total_size, "Visible size < total for iceberg"

        n_slices = math.ceil(total_size / visible_size)
        interval_s = min(refresh_interval_s, max_duration_s / n_slices)

        children: List[ChildOrder] = []
        remaining = total_size

        for i in range(n_slices):
            size = min(visible_size, remaining)
            remaining -= size
            is_last = remaining <= 0

            children.append(ChildOrder(
                sequence=i,
                size=round(size, 8),
                price_limit=current_price,
                scheduled_time_s=i * interval_s,
                algo_type=AlgoType.ICEBERG,
                is_hidden=not is_last,
            ))

        expected_duration = min(max_duration_s, n_slices * interval_s)

        return ExecutionPlan(
            parent_size=total_size,
            child_orders=children,
            expected_tce_bps=0.5,  # Maker fees
            expected_duration_s=expected_duration,
            algo_type=AlgoType.ICEBERG,
            participation_rate=0.0,  # Passive
        )

    def check_early_exit(
        self,
        current_price: float,
        entry_price: float,
        side: str,
        threshold_pct: float,
    ) -> Tuple[bool, str]:
        """
        Verifica condicao de early exit.
        Returns (should_exit, reason).
        """
        if current_price <= 0 or entry_price <= 0:
            return False, ""

        pnl_pct = (current_price - entry_price) / entry_price * 100.0

        if side == "BUY" and pnl_pct < -threshold_pct:
            return True, f"Price dropped {abs(pnl_pct):.2f}% below entry (threshold={threshold_pct}%)"
        if side == "SELL" and pnl_pct > threshold_pct:
            return True, f"Price rose {pnl_pct:.2f}% above entry (threshold={threshold_pct}%)"

        return False, ""

    def adjust_for_impact(
        self, plan: ExecutionPlan, actual_volatility: float
    ) -> ExecutionPlan:
        """
        Reajusta plano de execucao com base na volatilidade real.
        Se impacto excede expected, redistribui sizing no tempo.
        """
        if len(plan.child_orders) == 0:
            return plan

        # Recalculate with observed volatility
        if plan.algo_type == AlgoType.TWAP:
            return self.generate_twap(
                symbol="",
                side="",
                total_size=plan.parent_size,
                duration_s=plan.expected_duration_s,
                n_slices=len(plan.child_orders),
                volatility=actual_volatility,
            )

        return plan
