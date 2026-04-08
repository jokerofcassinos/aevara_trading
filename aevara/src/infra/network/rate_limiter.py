# @module: aevara.src.infra.network.rate_limiter
# @deps: asyncio, time, dataclasses, typing
# @status: IMPLEMENTED_v1.0
# @last_update: 2026-04-10
# @summary: Async TokenBucket rate limiter for institutional throughput management (Ψ-11).

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from aevara.src.telemetry.structured_logger import logger

class RateLimiter:
    """
    Limitador de Frequência Assíncrono (Token Bucket).
    Garante conformidade com limites de API (exchange/Telegram) com backoff automático.
    """
    def __init__(self, rate: float, burst: float):
        self.rate = rate # Tokens per second
        self.burst = burst # Max tokens
        self.tokens = burst
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Bloqueia até que um token esteja disponível (backoff manual)."""
        async with self._lock:
            now = time.time()
            # Refill tokens
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                logger.log("RATE_LIMIT", f"Backoff required: waiting {wait_time:.3f}s")
                await asyncio.sleep(wait_time)
                # Recalcular após o sleep
                self.tokens = 0.0
                self.last_update = time.time()
            else:
                self.tokens -= 1.0

class MultiEndpointRateLimiter:
    """Gerenciador de múltiplos buckets para diferentes endpoints."""
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}

    def setup_endpoint(self, name: str, rate: float, burst: float):
        self._limiters[name] = RateLimiter(rate, burst)

    async def throttle(self, endpoint: str):
        if endpoint in self._limiters:
            await self._limiters[endpoint].acquire()
        else:
            # Bypass para endpoints não configurados
            pass
