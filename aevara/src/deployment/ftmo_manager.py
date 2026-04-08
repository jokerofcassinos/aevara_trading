# @module: aevara.src.deployment.ftmo_manager
# @deps: dataclasses, typing, telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Immutably tracks FTMO constraints. Enforces hard blocks on violation. Conservatively armored at 80% of limits.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

@dataclass(frozen=True, slots=True)
class FTMOConfig:
    daily_loss_limit_pct: float = 0.04  # Initial buffer: 4% of day (FTMO is 5%)
    max_total_loss_pct: float = 0.08    # Initial buffer: 8% of account (FTMO is 10%)
    profit_target_pct: float = 0.08     # 8% Phase 1 Target
    min_trading_days: int = 4
    max_risk_per_trade_pct: float = 0.01 # 1% internal self-restriction
    initial_balance: float = 100000.0

@dataclass(slots=True)
class FTMOChallengeState:
    current_equity: float
    daily_start_equity: float
    high_water_mark: float
    trading_days: int
    is_halted: bool = False
    halt_reason: str = ""

class FTMOManager:
    """
    Fiscal Implacável da FTMO (v1.0).
    Executa monitoramento em tempo real de Equity/Drawdown.
    O método is_safe_to_trade decide o destino simbólico do bot.
    """
    def __init__(self, config: FTMOConfig = FTMOConfig()):
        self._config = config
        self._state = FTMOChallengeState(
            current_equity=config.initial_balance,
            daily_start_equity=config.initial_balance,
            high_water_mark=config.initial_balance,
            trading_days=0
        )

    def update_state(self, equity: float, daily_reset: bool = False) -> None:
        """Atualiza o estado do desafio (HWM, Equity, Daily Reset)."""
        self._state.current_equity = equity
        if equity > self._state.high_water_mark:
             self._state.high_water_mark = equity
        
        if daily_reset:
             self._state.daily_start_equity = equity
             self._state.trading_days += 1

    def is_safe_to_trade(self) -> Tuple[bool, str]:
        """
        Verifica se a conta está dentro dos perímetros de segurança FTMO.
        Bloqueio imediato se Drawdown diário > 4% ou total > 8%.
        """
        if self._state.is_halted:
             return False, self._state.halt_reason
        
        # 1. Daily Drawdown Check (Hard Buffer)
        daily_dd = (self._state.daily_start_equity - self._state.current_equity) / self._state.daily_start_equity
        if daily_dd >= self._config.daily_loss_limit_pct:
             self._state.is_halted = True
             self._state.halt_reason = f"FTMO ALERT: Daily Drawdown Limit ({daily_dd*100:.2f}%) exceeded buffer 4.0%."
             return False, self._state.halt_reason
             
        # 2. Total Drawdown Check (Hard Buffer)
        total_dd = (self._config.initial_balance - self._state.current_equity) / self._config.initial_balance
        if total_dd >= self._config.max_total_loss_pct:
             self._state.is_halted = True
             self._state.halt_reason = f"FTMO ALERT: Total Drawdown Limit ({total_dd*100:.2f}%) exceeded buffer 8.0%."
             return False, self._state.halt_reason

        return True, "SYSTEM_SAFE: Within FTMO parameters."

    def check_profit_target_reached(self) -> bool:
        """Verifica se o alvo de lucro da Fase 1 foi atingido."""
        profit = (self._state.current_equity - self._config.initial_balance) / self._config.initial_balance
        return profit >= self._config.profit_target_pct

    def get_risk_budget(self) -> float:
        """Retorna o orçamento de risco sugerido em percentual da equity."""
        # Se lucro estiver próximo da meta, reduz risco para 'fechar o dia'
        if self.check_profit_target_reached(): return 0.0
        
        # Orçamento dinâmico baseado no buffer restante
        daily_remain = self._config.daily_loss_limit_pct - ((self._state.daily_start_equity - self._state.current_equity) / self._state.daily_start_equity)
        return max(0.0, min(self._config.max_risk_per_trade_pct, daily_remain / 2.0))
