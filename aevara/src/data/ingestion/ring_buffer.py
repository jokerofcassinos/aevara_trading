# @module: aevara.src.data.ingestion.ring_buffer
# @deps: None
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Ring buffer bounded e lock-free para ticks validados.
#           Capacidade fixa. Quando cheio, descarta mais antigo (O(1)).

from __future__ import annotations

from collections import deque
from typing import Any, Generic, Iterator, Optional, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    """
    Ring buffer bounded com comportamento FIFO.
    Quando cheio, o elemento mais antigo e descartado automaticamente.
    Nao e verdadeiramente lock-free em Python (GIL), mas garante O(1)
    para push/pop e memoria bounded.

    Invariantes:
    - len(buffer) <= capacity
    - push/pop sao O(1) amortized
    """

    def __init__(self, capacity: int = 5000):
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        self._capacity = capacity
        self._buffer: deque[T] = deque(maxlen=capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def is_full(self) -> bool:
        return len(self._buffer) >= self._capacity

    @property
    def is_empty(self) -> bool:
        return len(self._buffer) == 0

    def push(self, item: T) -> Optional[T]:
        """
        Push item ao buffer. Se cheio, retorna o elemento descartado.
        O(1) amortized.
        """
        evicted = None
        if self.is_full:
            evicted = self._buffer[0]
        self._buffer.append(item)
        return evicted

    def pop(self) -> Optional[T]:
        """Pop oldest item. O(1)."""
        if self.is_empty:
            return None
        return self._buffer.popleft()

    def peek(self) -> Optional[T]:
        """Peek oldest item without removing. O(1)."""
        if self.is_empty:
            return None
        return self._buffer[0]

    def peek_latest(self) -> Optional[T]:
        """Peek latest item without removing. O(1)."""
        if self.is_empty:
            return None
        return self._buffer[-1]

    def get_all(self) -> list[T]:
        """Return all items in order (oldest first). O(n)."""
        return list(self._buffer)

    def get_last_n(self, n: int) -> list[T]:
        """Return last n items. O(n)."""
        if n >= len(self._buffer):
            return list(self._buffer)
        return list(self._buffer)[-n:]

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    def __iter__(self) -> Iterator[T]:
        return iter(self._buffer)
