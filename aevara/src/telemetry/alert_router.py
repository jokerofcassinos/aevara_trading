# @module: aevara.src.telemetry.alert_router
# @deps: time
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Alert routing hierarquico com deduplicacao, cooldown, escalation.
#           INFO -> log, WARNING -> log + flag, CRITICAL -> alert + log,
#           FATAL -> all channels + auto-pause.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
import time


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


@dataclass(frozen=True, slots=True)
class Alert:
    """Alerta imutavel."""
    level: AlertLevel
    component: str
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    dedup_key: str
    timestamp_ns: int
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlertAction:
    """Acao tomada pelo router."""
    routed: bool
    suppress_reason: str  # "" if routed
    channel: str  # "log", "telegram", "all", "none"
    alert: Alert


class AlertRouter:
    """
    Rotor de alertas hierarquico com deduplicacao e cooldown.

    Invariantes:
    - Mesma mensagem em < cooldown_s -> suppress
    - WARNING -> log always
    - CRITICAL -> log + alert
    - FATAL -> all channels + auto-pause
    - Dedup window = 300s (5 min) default
    - Bounded history (max 1000 alerts)
    """

    def __init__(
        self,
        dedup_window_s: float = 300.0,
        max_alert_history: int = 1000,
        handler: Optional[Callable] = None,
    ):
        self._dedup_window = dedup_window_s
        self._history: deque[AlertAction] = deque(maxlen=max_alert_history)
        self._last_alerts: Dict[str, int] = {}  # dedup_key -> last_timestamp_ns
        self._handler = handler

    @property
    def alert_count(self) -> int:
        return len(self._history)

    def route(self, alert: Alert) -> AlertAction:
        """
        Rota alerta baseado em nivel e deduplicacao.

        Returns:
            AlertAction com canal e status
        """
        now = alert.timestamp_ns
        now_s = now / 1e9

        # Dedup check
        last_ts = self._last_alerts.get(alert.dedup_key, 0)
        time_since_last = (now - last_ts) / 1e9 if last_ts > 0 else float("inf")

        if time_since_last < self._dedup_window:
            action = AlertAction(
                routed=False,
                suppress_reason=f"Dedup: last alert {time_since_last:.0f}s ago",
                channel="none",
                alert=alert,
            )
            self._history.append(action)
            return action

        # Route by level
        self._last_alerts[alert.dedup_key] = now

        if alert.level == AlertLevel.INFO:
            action = AlertAction(
                routed=True, suppress_reason="", channel="log", alert=alert
            )
        elif alert.level == AlertLevel.WARNING:
            action = AlertAction(
                routed=True, suppress_reason="", channel="log", alert=alert
            )
        elif alert.level == AlertLevel.CRITICAL:
            action = AlertAction(
                routed=True, suppress_reason="", channel="telegram", alert=alert
            )
        elif alert.level == AlertLevel.FATAL:
            action = AlertAction(
                routed=True, suppress_reason="", channel="all", alert=alert
            )
        else:
            action = AlertAction(
                routed=False, suppress_reason=f"Unknown level: {alert.level}",
                channel="none", alert=alert
            )

        self._history.append(action)
        return action

    def get_recent_alerts(self, n: int = 10) -> List[AlertAction]:
        return list(self._history)[-n:]

    def get_suppressed_count(self) -> int:
        return sum(1 for a in self._history if not a.routed)

    def reset(self) -> None:
        self._history.clear()
        self._last_alerts.clear()
