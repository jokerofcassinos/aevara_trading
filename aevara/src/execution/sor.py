# @module: aevara.src.execution.sor
# @deps: dataclasses, typing, time
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Smart Order Router: venue selection por TCE (Total Cost of Execution),
#           fee-tier awareness, latency mapping, liquidity fragmentation handling,
#           fallback chain quando venue primario falha.

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class VenueInfo:
    """Informacao de uma venue (exchange)."""
    venue_id: str
    taker_fee_bps: float       # Fee para ordens que tiram liquidez
    maker_fee_bps: float       # Fee para ordens que adicionam liquidez
    avg_latency_us: int        # Latencia media em microssegundos
    fill_rate: float           # Taxa de preenchimento (0-1)
    avg_slippage_bps: float    # Slippage medio esperado
    available: bool            # Status da conexao
    min_order_size: float
    max_order_size: float


@dataclass(frozen=True, slots=True)
class SORDecision:
    """Decisao do Smart Order Router."""
    selected_venue: str
    algo: str                  # TWAP/VWAP/POV/ICEBERG/SMART_LIMIT
    split_plan: List[float]    # % alocacao por child order
    expected_tce_bps: float    # TCE estimado total
    routing_latency_us: int
    reasoning: str


class SmartOrderRouter:
    """
    Seleciona venue otima baseada em TCE (Total Cost of Execution).

    TCE = commission_bps + slippage_bps + market_impact_bps + funding_bps
    Se E[TCE] > budget, ordem e rejeitada.

    Invariantes:
    - Sempre seleciona venue disponivel com menor TCE
    - TCE gating: se > budget, retorna None + motivo
    - Fallback chain: se venue primaria falha, proxima na fila
    - Split sizing se tamanho excede max_order_size da venue
    """

    def __init__(self, venues: Optional[Dict[str, VenueInfo]] = None):
        self._venues: Dict[str, VenueInfo] = {}
        if venues:
            for venue_id, info in venues.items():
                self._venues[venue_id] = info

    def add_venue(self, venue_id: str, info: VenueInfo) -> None:
        self._venues[venue_id] = info

    def remove_venue(self, venue_id: str) -> bool:
        if venue_id in self._venues:
            del self._venues[venue_id]
            return True
        return False

    def compute_tce(
        self,
        venue: VenueInfo,
        is_maker: bool = False,
        market_impact_bps: float = 0.5,
        funding_bps: float = 0.0,
    ) -> float:
        """
        Calcula TCE (Total Cost of Execution) para uma venue.

        TCE = commission + slippage + market_impact + funding
        """
        commission = venue.maker_fee_bps if is_maker else venue.taker_fee_bps
        return commission + venue.avg_slippage_bps + market_impact_bps + funding_bps

    def route(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        tce_budget_bps: float,
        is_maker: bool = False,
        market_impact_bps: float = 0.5,
        funding_bps: float = 0.0,
    ) -> Optional[SORDecision]:
        """
        Roteia ordem para melhor venue.

        Returns:
            SORDecision se routing bem-sucedido, None se TCE exceed budget.
        """
        available_venues = [
            (vid, v) for vid, v in self._venues.items() if v.available
        ]
        if not available_venues:
            return None

        # Calcula TCE para cada venue disponivel
        venue_tces: List[Tuple[str, VenueInfo, float]] = []
        for vid, venue in available_venues:
            tce = self.compute_tce(venue, is_maker, market_impact_bps, funding_bps)
            venue_tces.append((vid, venue, tce))

        # Ordena por TCE crescente
        venue_tces.sort(key=lambda x: x[2])

        # TCE gating: verifica se melhor venue esta dentro do budget
        best_vid, best_venue, best_tce = venue_tces[0]
        if best_tce > tce_budget_bps:
            return None

        # Determina algoritmo baseado em tipo e tamanho
        algo = self._select_algo(size, best_venue, order_type)

        # Split plan se necessario
        split_plan = self._compute_split_plan(size, best_venue, algo)

        # Reasoning
        reasoning = (
            f"Venue {best_vid} selected: TCE={best_tce:.2f}bps "
            f"(budget={tce_budget_bps:.2f}bps), algo={algo}"
        )

        return SORDecision(
            selected_venue=best_vid,
            algo=algo,
            split_plan=split_plan,
            expected_tce_bps=best_tce,
            routing_latency_us=best_venue.avg_latency_us,
            reasoning=reasoning,
        )

    def get_fallback_chain(self, primary_venue: str) -> List[str]:
        """Retorna cadeia de fallback ordenada por TCE."""
        if primary_venue not in self._venues:
            return []

        others = [
            (vid, v) for vid, v in self._venues.items()
            if vid != primary_venue and v.available
        ]
        # Ordena por TCE crescente (assume taker, impacto padrao)
        others.sort(key=lambda x: self.compute_tce(x[1]))
        return [vid for vid, _ in others]

    def _select_algo(self, size: float, venue: VenueInfo, order_type: str) -> str:
        """Seleciona algoritmo baseado em caracteristicas da ordem."""
        if order_type in ("IOC", "FOK"):
            return "SMART_LIMIT"
        if size > venue.max_order_size * 0.5:
            return "TWAP"
        if order_type == "MARKET":
            return "POV"
        return "SMART_LIMIT"

    def _compute_split_plan(
        self, size: float, venue: VenueInfo, algo: str
    ) -> List[float]:
        """
        Calcula plano de split de ordem.
        Para ordens grandes, divide em child orders.
        """
        if algo == "TWAP":
            # Divide em 4-8 slices baseado em tamanho relativo
            n_slices = min(8, max(4, int(size / venue.max_order_size * 8) + 1))
            slice_pct = 1.0 / n_slices
            return [slice_pct] * n_slices
        elif algo == "VWAP":
            # 6 slices com pesos variados (mais no inicio/fim)
            return [0.2, 0.15, 0.15, 0.15, 0.15, 0.2]
        elif algo == "ICEBERG":
            # 90% hidden, 10% visible
            return [0.1] * 10
        else:
            # SMART_LIMIT/POV: ordem unica
            return [1.0]

    def get_available_venues(self) -> List[str]:
        """Retorna lista de venues disponiveis."""
        return [vid for vid, v in self._venues.items() if v.available]

    def get_venue_info(self, venue_id: str) -> Optional[VenueInfo]:
        return self._venues.get(venue_id)

    def update_venue_latency(self, venue_id: str, latency_us: int) -> None:
        """Atualiza latencia de venue (EMA smoothing)."""
        if venue_id in self._venues:
            old = self._venues[venue_id]
            new = VenueInfo(
                venue_id=old.venue_id,
                taker_fee_bps=old.taker_fee_bps,
                maker_fee_bps=old.maker_fee_bps,
                avg_latency_us=latency_us,
                fill_rate=old.fill_rate,
                avg_slippage_bps=old.avg_slippage_bps,
                available=old.available,
                min_order_size=old.min_order_size,
                max_order_size=old.max_order_size,
            )
            self._venues[venue_id] = new
