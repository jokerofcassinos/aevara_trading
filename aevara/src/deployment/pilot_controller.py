# @module: aevara.src.deployment.pilot_controller
# @deps: typing, dataclasses, time
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Pilot Controller update: sizing lock (0.01 lots) until unlock by ActivationOrchestrator. Stability validation per trade count.

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple

class PilotController:
    """
    Controlador Piloto (v1.0.0).
    Garante o bloqueio imutável de sizing (0.01 lotes) durante a ativação.
    Impede tentativas de scaling prematuro em fases iniciais.
    """
    def __init__(self, initial_lot: float = 0.01):
        self._is_locked = True
        self._lock_lot = initial_lot
        self._trades_completed = 0
        self._stability_score = 1.0 # [0,1]

    async def lock_sizing(self, lot: float = 0.01):
        """Ativa o bloqueio de sizing administrativo."""
        self._is_locked = True
        self._lock_lot = lot
        print(f"AEVRA PILOT: Sizing locked at {lot:.2f} lots.")

    async def unlock_sizing(self):
        """Remove o bloqueio administrativo de sizing."""
        self._is_locked = False
        print("AEVRA PILOT: Sizing UNLOCKED. Adaptive scaling active.")

    def get_authorized_size(self, proposed_size: float) -> float:
        """
        Retorna o tamanho autorizado.
        Se locked -> retorna lock_lot (0.01).
        Qualquer desvio se locked dispara um alerta P0.
        """
        if self._is_locked:
             if proposed_size != self._lock_lot:
                  print(f"AEVRA PILOT ALERT: Attempted sizing override ({proposed_size:.2f} != {self._lock_lot:.2f}). Restricting 0.01.")
             return self._lock_lot
        return proposed_size

    def record_trade(self, pnl: float):
        """Registra estabilidade e contagem de trades."""
        self._trades_completed += 1
        # Calculo simplificado de estabilidade
        self._stability_score = min(1.0, self._trades_completed / 50.0)

    def is_locked(self) -> bool:
        return self._is_locked

    def get_stability_status(self) -> Dict:
        return {
            "is_locked": self._is_locked,
            "trades_completed": self._trades_completed,
            "stability_score": self._stability_score
        }
