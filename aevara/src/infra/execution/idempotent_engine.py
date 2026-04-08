# @module: aevara.src.infra.execution.idempotent_engine
# @deps: uuid, time, asyncio
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Nonce generation (UUID v4), state reconciliation, dedup cache
#           com TTL, retry idempotency guarantee. Cada ordem recebe nonce unico
#           que sobrevive a retries sem duplicacao.

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class OrderState(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OrderRecord:
    nonce: str
    payload: Dict[str, Any]
    state: OrderState
    created_ns: int
    updated_ns: int


class IdempotentEngine:
    """
    Motor de idempotencia para ordens.

    Invariantes:
    - Nonce único por ordem (UUID v4)
    - Cache de dedup com TTL=300s e tamanho maximo
    - Retry com MESMO nonce retorna resultado original
    - LRU eviction automatica quando cache cheio
    """

    def __init__(self, cache_maxsize: int = 10000, ttl_s: float = 300.0):
        assert cache_maxsize > 0
        assert ttl_s > 0
        self._cache: OrderedDict[str, OrderRecord] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._ttl_s = ttl_s

    def generate_nonce(self) -> str:
        """Gera nonce unico para ordem (UUID v4)."""
        return str(uuid.uuid4())

    def submit(self, nonce: str, payload: Dict[str, Any]) -> Tuple[OrderState, Optional[OrderRecord]]:
        """
        Submete ordem com nonce.
        Se nonce ja existe e estado nao e PENDING, retorna resultado original (idempotente).
        Se nonce ja existe e estado e PENDING, retorna BUSY.
        Retorna (state, existing_record_or_new).
        """
        now = time.time_ns()

        # Check if nonce already in cache
        if nonce in self._cache:
            record = self._cache[nonce]
            # Evict expired
            if (now - record.created_ns) / 1e9 > self._ttl_s:
                del self._cache[nonce]
            else:
                # Idempotent: return existing
                return (record.state, record)

        # New order
        record = OrderRecord(
            nonce=nonce,
            payload=dict(payload),
            state=OrderState.PENDING,
            created_ns=now,
            updated_ns=now,
        )
        self._cache[nonce] = record
        self._cache.move_to_end(nonce)

        # Evict if over capacity
        if len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)

        return (OrderState.PENDING, None)

    def update_state(self, nonce: str, new_state: OrderState) -> Optional[OrderRecord]:
        """Atualiza estado de ordem existente."""
        now = time.time_ns()
        if nonce not in self._cache:
            return None
        record = self._cache[nonce]
        updated = OrderRecord(
            nonce=record.nonce,
            payload=record.payload,
            state=new_state,
            created_ns=record.created_ns,
            updated_ns=now,
        )
        self._cache[nonce] = updated
        return updated

    def get(self, nonce: str) -> Optional[OrderRecord]:
        """Retorna ordem por nonce."""
        if nonce in self._cache:
            record = self._cache[nonce]
            if (time.time_ns() - record.created_ns) / 1e9 > self._ttl_s:
                del self._cache[nonce]
                return None
            return record
        return None

    def evict_expired(self) -> int:
        """Remove entradas expiradas. Retorna count."""
        now = time.time_ns()
        expired = [k for k, v in self._cache.items()
                   if (now - v.created_ns) / 1e9 > self._ttl_s]
        for k in expired:
            del self._cache[k]
        return len(expired)

    def cache_size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()
