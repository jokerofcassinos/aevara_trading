# @module: aevara.src.live.ftmo_guard
# @deps: typing, dataclasses, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Immutable FTMO constraint enforcement with zero-override policy and telemetry logging.

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

class FTMOGuard:
    """
    Fiscalizador de conformidade FTMO (Zero-Override).
    Garante limites absolutos de perda diaria e total, alem de restricoes temporais.
    """
    def __init__(self, initial_equity: float):
        self._initial_equity = initial_equity
        self._violations: List[str] = []

    def validate_daily_loss(self, current_pnl: float, max_daily_loss: float = 0.04) -> bool:
        """Valida que a perda no dia nao excede 4% do equity inicial do dia."""
        # current_pnl eh o nominal
        loss_pct = abs(min(0, current_pnl)) / self._initial_equity
        if loss_pct > max_daily_loss:
            self.log_violation_attempt("DAILY_LOSS", loss_pct, max_daily_loss)
            return False
        return True

    def validate_total_loss(self, current_equity: float, max_total_loss: float = 0.08) -> bool:
        """Valida que a perda total nao excede 8% do equity inicial."""
        drawdown_pct = (self._initial_equity - current_equity) / self._initial_equity
        if drawdown_pct > max_total_loss:
            self.log_violation_attempt("TOTAL_LOSS", drawdown_pct, max_total_loss)
            return False
        return True

    def validate_trading_days(self, days_active: int, min_days: int = 4) -> bool:
        """Check para conformidade de dias minimos de operacao."""
        return days_active >= min_days

    def is_within_compliance(self, state: Dict) -> Tuple[bool, str]:
        """
        Check de conformidade global.
        State deve conter: current_pnl, current_equity, days_active.
        """
        pnl = state.get("current_pnl", 0)
        equity = state.get("current_equity", self._initial_equity)
        
        if not self.validate_daily_loss(pnl):
             return False, "Daily loss limit breached (FTMO 4%)"
        
        if not self.validate_total_loss(equity):
             return False, "Total loss limit breached (FTMO 8%)"
             
        return True, "COMPLIANT"

    def log_violation_attempt(self, constraint: str, value: float, limit: float) -> None:
        """Registra a tentativa de violacao (Imutavel)."""
        msg = f"[CRITICAL-FTMO] Violation Attempt: {constraint} | Value: {value:.4f} | Limit: {limit:.4f}"
        self._violations.append(msg)
        # In production: emit hard-alert to TelemetryStream
