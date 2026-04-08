# @module: aevara.src.interfaces.alert_router
# @deps: typing, asyncio, time, hashlib
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Hierarchical, deduplicated, cooldown-aware routing with escalation and quiet hours.

from __future__ import annotations
import asyncio
import time
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Set

class AlertRouter:
    """
    Roteador de alertas hierarquico com suporte a deduplicacao (dedup),
    escalonamento e janelas de silencio (quiet hours).
    """
    def __init__(self, dedup_window_s: int = 300):
        self._dedup_window = dedup_window_s
        self._active_alerts: Dict[str, float] = {} # hash -> last_seen_ts
        self._alert_counts: Dict[str, int] = {}    # hash -> count
        self._quiet_hours: Optional[Tuple[str, str]] = None # (HH:MM, HH:MM) UTC
        self._handlers: Dict[str, List[Any]] = {
            "INFO": [],
            "WARNING": [],
            "CRITICAL": [],
            "FATAL": []
        }

    def register_handler(self, level: str, handler: Any) -> None:
        if level in self._handlers:
            self._handlers[level].append(handler)

    async def route(self, level: str, component: str, message: str, context: Optional[Dict] = None) -> None:
        """
        Roteia o alerta para os handlers registrados, aplicando filtros e dedup.
        """
        alert_hash = self._generate_hash(level, component, message)
        
        if self._is_quiet_hour():
            if level in ("INFO", "WARNING"):
                return

        if self.is_suppressed(alert_hash):
            self._alert_counts[alert_hash] = self._alert_counts.get(alert_hash, 0) + 1
            return

        self._active_alerts[alert_hash] = time.time()
        self._alert_counts[alert_hash] = 1
        
        full_msg = f"[{level}] {component}: {message}"
        if self._alert_counts.get(alert_hash, 0) > 1:
            full_msg += f" (seen {self._alert_counts[alert_hash]} times)"

        # Dispatch to handlers
        for handler in self._handlers.get(level, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(level, full_msg, context or {})
                else:
                    handler(level, full_msg, context or {})
            except Exception:
                pass # Fail silently or log to local disk

    def is_suppressed(self, alert_hash: str) -> bool:
        """Janela de 300s para alertas identicos."""
        last_seen = self._active_alerts.get(alert_hash, 0)
        return (time.time() - last_seen) < self._dedup_window

    def escalate(self, alert_hash: str) -> str:
        """Escalona o nivel do alerta se repetir muito."""
        count = self._alert_counts.get(alert_hash, 0)
        if count > 50: return "FATAL"
        if count > 10: return "CRITICAL"
        return "WARNING"

    def set_quiet_hours(self, start: str, end: str) -> None:
        """Define horas de silencio (ex: '23:00' to '04:00' UTC)."""
        self._quiet_hours = (start, end)

    def _is_quiet_hour(self) -> bool:
        if not self._quiet_hours:
            return False
        
        current_time = time.strftime("%H:%M", time.gmtime())
        start, end = self._quiet_hours
        if start <= end:
            return start <= current_time <= end
        else: # Overnight
            return current_time >= start or current_time <= end

    def _generate_hash(self, level: str, component: str, message: str) -> str:
        raw = f"{level}:{component}:{message}"
        return hashlib.sha256(raw.encode()).hexdigest()
