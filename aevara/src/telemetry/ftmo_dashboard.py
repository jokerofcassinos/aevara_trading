# @module: aevara.src.telemetry.ftmo_dashboard
# @deps: typing, time, deployment.ftmo_manager
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Real-time FTMO Challenge Progress Dashboard: Profit targets, Drawdown bars, and Time constraints.

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple
from aevara.src.deployment.ftmo_manager import FTMOManager

class FTMODashboard:
    """
    O 'Painel de Guerra' do Desafio FTMO (v1.0).
    Visualiza em tempo real a progressão para o alvo e a distância dos limites fatais.
    Emite métricas para o TelemetryStream.
    """
    def __init__(self, ftmo_manager: FTMOManager):
        self._manager = ftmo_manager

    def render(self):
        """Renderiza barra de progresso e métricas críticas no terminal/telemetria."""
        state = self._manager._state
        config = self._manager._config
        
        # Alvo de Lucro
        profit = (state.current_equity - config.initial_balance)
        target = config.initial_balance * config.profit_target_pct
        progress = max(0.0, min(100.0, (profit / target) * 100.0))
        
        # Drawdown Diário (Distância do Abismo)
        daily_dd = (state.daily_start_equity - state.current_equity) / state.daily_start_equity
        daily_limit = config.daily_loss_limit_pct
        daily_bar = (daily_dd / daily_limit) * 100.0
        
        # Total Drawdown
        total_dd = (config.initial_balance - state.current_equity) / config.initial_balance
        total_limit = config.max_total_loss_pct
        total_bar = (total_dd / total_limit) * 100.0
        
        # Status Output
        print("\n" + "="*50)
        print(f" 🏆 AEVRA — FTMO CHALLENGE STATUS (v1.0) ".center(50, " "))
        print("="*50)
        print(f" ACCOUNT: ${state.current_equity:,.2f} | HWM: ${state.high_water_mark:,.2f}")
        print(f" PROFIT: ${profit:+,.2f} | TARGET: ${target:,.2f} ({progress:0.1f}%)")
        print(f" PROGRESS: [{'#'*int(progress/2)}{'-'*(50-int(progress/2))}]")
        print("-"*50)
        print(f" DAILY DD: {daily_dd*100:0.2f}% / {daily_limit*100:0.1f}% | RISK: [{'!'*int(daily_bar/2)}{' '*(50-int(daily_bar/2))}]")
        print(f" TOTAL DD: {total_dd*100:0.2f}% / {total_limit*100:0.1f}% | RISK: [{'!'*int(total_bar/2)}{' '*(50-int(total_bar/2))}]")
        print(f" TRADING DAYS: {state.trading_days} / {config.min_trading_days}")
        
        if state.is_halted:
             print(f" !!! STATUS: BLOCKED - {state.halt_reason} !!!")
        elif progress >= 100.0:
             print(" !!! STATUS: TARGET REACHED - PASS DETECTED !!!")
        else:
             print(" STATUS: ACTIVE & MONITORING")
        print("="*50 + "\n")
