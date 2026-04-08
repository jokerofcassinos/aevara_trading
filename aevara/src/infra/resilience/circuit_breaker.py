# @module: aevara.src.infra.resilience.circuit_breaker
# @deps: time, asyncio
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Circuit breaker com state machine deterministico (CLOSED/OPEN/HALF_OPEN),
#           failure threshold configurable, recovery validation via probe call,
#           metrics export, bounded memory.

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Type


class CBState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout_s: float = 30.0
    half_open_max_calls: int = 3
    monitored_errors: Tuple[Type[Exception], ...] = (Exception,)


@dataclass(frozen=True, slots=True)
class CircuitBreakerMetrics:
    calls: int
    successes: int
    failures: int
    consecutive_failures: int
    state: CBState
    last_failure_ts: Optional[float] = None
    half_open_calls: int = 0


class CircuitBreaker:
    """
    Circuit breaker com state machine deterministico.

    Invariantes:
    - CLOSED -> OPEN quando failures >= threshold
    - OPEN -> HALF_OPEN apos recovery_timeout
    - HALF_OPEN -> CLOSED se probing success, OPEN se failure
    - Transicoes baseadas em contadores (deterministico)
    - Metrics export com bounded history
    """

    def __init__(self, name: str = "default", config: Optional[CircuitBreakerConfig] = None):
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CBState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._consecutive_failures = 0
        self._total_calls = 0
        self._last_failure_ts: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._half_open_calls = 0
        self._history: deque[Dict] = deque(maxlen=500)

    @property
    def state(self) -> CBState:
        """Estado com auto-transicao OPEN -> HALF_OPEN se timeout expirou."""
        if self._state == CBState.OPEN and self._opened_at is not None:
            if time.time() - self._opened_at >= self._config.recovery_timeout_s:
                return CBState.HALF_OPEN
        return self._state

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "calls": self._total_calls,
            "successes": self._success_count,
            "failures": self._failure_count,
            "consecutive_failures": self._consecutive_failures,
            "state": self.state.value,
            "last_failure_ts": self._last_failure_ts,
            "half_open_calls": self._half_open_calls,
        }

    async def call(self, func, *args: Any, **kwargs: Any) -> Any:
        """
        Executa funcao com circuit breaker.

        Raises:
            CircuitBreakerError: Se circuito OPEN
        """
        current_state = self.state

        if current_state == CBState.OPEN:
            raise CircuitBreakerError(
                f"CircuitBreaker '{self._name}' is OPEN. "
                f"Recovery in {self._config.recovery_timeout_s}s"
            )

        if current_state == CBState.HALF_OPEN:
            if self._half_open_calls >= self._config.half_open_max_calls:
                raise CircuitBreakerError(
                    f"CircuitBreaker '{self._name}' HALF_OPEN max probes reached"
                )
            self._half_open_calls += 1

        self._total_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except self._config.monitored_errors as e:
            self._on_failure(e)
            raise

    def _on_success(self) -> None:
        self._success_count += 1
        self._consecutive_failures = 0
        if self.state == CBState.HALF_OPEN:
            # Success in HALF_OPEN -> CLOSE
            self._state = CBState.CLOSED
            self._half_open_calls = 0
            self._failure_count = 0
            self._consecutive_failures = 0

    def _on_failure(self, error: Exception) -> None:
        self._failure_count += 1
        self._consecutive_failures += 1
        self._last_failure_ts = time.time()

        self._history.append({
            "ts": self._last_failure_ts,
            "state": self.state.value,
            "error": str(error),
        })

        if self.state != CBState.HALF_OPEN:
            if self._consecutive_failures >= self._config.failure_threshold:
                self._state = CBState.OPEN
                self._opened_at = time.time()
        else:
            # Failure in HALF_OPEN -> OPEN again
            self._state = CBState.OPEN
            self._opened_at = time.time()
            self._half_open_calls = 0

    def reset(self) -> None:
        self._state = CBState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._consecutive_failures = 0
        self._half_open_calls = 0
        self._opened_at = None
        self._last_failure_ts = None

    def get_history(self) -> List[Dict]:
        return list(self._history)


class CircuitBreakerError(Exception):
    """Excecao lançada quando circuito esta OPEN ou HALF_OPEN saturado."""
    pass
