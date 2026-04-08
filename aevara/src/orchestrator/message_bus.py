# @module: aevara.src.orchestration.message_bus
# @deps: asyncio, typing, collections
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: High-performance, async-first message bus for inter-modular communication (Ψ-11). Supports pub/sub with bounded queues.

from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

class MessageBus:
    """
    AEVRA Message Bus (v1.0.0).
    Facilita a comunicação desacoplada entre os módulos Ω e Ψ.
    """
    def __init__(self, max_queue_size: int = 500):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """Subscreve a um tópico e retorna a fila de mensagens."""
        queue = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._subscribers[topic].add(queue)
        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        """Cancela a subscrição de um tópico."""
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(queue)

    async def publish(self, topic: str, message: Any):
        """Publica uma mensagem em um tópico."""
        if topic not in self._subscribers:
            return

        async with self._lock:
            # Envia para todos os inscritos
            for queue in self._subscribers[topic]:
                if queue.full():
                    try:
                        queue.get_nowait() # Drop oldest if full (Ψ-11 protocol)
                    except asyncio.QueueEmpty:
                        pass
                await queue.put(message)

# Global Instance
bus = MessageBus()
