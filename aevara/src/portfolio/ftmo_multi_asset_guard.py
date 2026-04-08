# @module: aevara.src.portfolio.ftmo_multi_asset_guard
# @deps: typing, time
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Aggregate FTMO compliance enforcement across multiple assets with propagation halt logic. Σ ≤ 5.0 lots, 4% Daily DD, 8% Total DD.

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple

class FTMOMultiAssetGuard:
    """
    O 'Tribunal Multi-Ativo' (v1.0.0).
    Aplica as regras imutáveis da FTMO de forma agregada para o conjunto BTC/ETH/SOL.
    Impõe halt_propagation: se um ativo viola, TODOS os ativos param imediatamente.
    """
    def __init__(self, 
                 daily_limit_pct: float = 0.04, 
                 total_limit_pct: float = 0.08, 
                 max_exposure_lots: float = 5.0):
        self._daily_limit = daily_limit_pct
        self._total_limit = total_limit_pct
        self._max_lots = max_exposure_lots
        self._is_halted = False
        self._halt_reason = ""

    def check_aggregate_exposure(self, positions: Dict[str, float]) -> Tuple[bool, str]:
        """Verifica se a soma dos lotes (abs) viola o teto de 5.0."""
        if self._is_halted: return False, self._halt_reason
        
        total_lots = sum(abs(v) for v in positions.values())
        if total_lots > self._max_lots:
             self.propagate_halt_if_breached("EXPOSURE_CAP", f"Total: {total_lots:.2f} > {self._max_lots}")
             return False, self._halt_reason
        return True, "EXPOSURE_SAFE"

    def check_cross_asset_drawdown(self, daily_pnl: float, current_equity: float, initial_balance: float) -> bool:
        """Monitora DD diário e total agregados entre todos os ativos do portfólio."""
        daily_dd = abs(min(0.0, daily_pnl)) / initial_balance # Simplificado
        total_dd = (initial_balance - current_equity) / initial_balance
        
        if daily_dd >= self._daily_limit or total_dd >= self._total_limit:
             self.propagate_halt_if_breached("DRAWDOWN_BREACH", f"DD Daily {daily_dd*100:.2f}% / Total {total_dd*100:.2f}%")
             return False
        return True

    def propagate_halt_if_breached(self, breach_type: str, details: str) -> bool:
        """Congela a operação global do organismo se um breach for detectado."""
        self._is_halted = True
        self._halt_reason = f"AEVRA FTMO HALT: {breach_type} | {details}"
        print(f"AEVRA GUARD: CRITICAL HALT PROPAGATED -> {self._halt_reason}")
        return True

    def get_remaining_capacity(self, current_lots: float) -> float:
        """Retorna quanto lote ainda pode ser alocado [0, 5.0]."""
        return max(0.0, self._max_lots - current_lots)
        
    def is_halted(self) -> bool:
        return self._is_halted
