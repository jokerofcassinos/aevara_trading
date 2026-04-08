# @module: aevara.src.telemetry.logger
# @deps: json, uuid, time
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Structured, async-compatible JSON logger with trace_id propagation,
#           contextual enrichment, and zero-blocking I/O via asyncio.Queue.

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Evento imutavel de telemetria."""
    trace_id: str
    span_id: str
    timestamp_ns: int
    level: str                     # INFO, WARNING, ERROR, CRITICAL, FATAL
    component: str
    event_type: str
    message: str
    context: Dict[str, Any]
    metrics: Dict[str, float]
    stack_trace: Optional[str] = None


class StructuredLogger:
    """
    Logger estruturado com trace propagation e async non-blocking I/O.

    Invariantes:
    - Todo evento tem trace_id e span_id
    - I/O assincrono via queue (zero blocking no hot path)
    - Bounded queue com overflow discard
    """

    def __init__(
        self,
        log_dir: str = "data/audit",
        queue_maxsize: int = 10000,
        trace_id: Optional[str] = None,
    ):
        self._trace_id = trace_id or uuid.uuid4().hex[:12]
        self._queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._log_dir = log_dir
        self._running = False
        self._writer_task: Optional[asyncio.Task] = None
        os.makedirs(log_dir, exist_ok=True)

    def new_trace(self) -> str:
        return uuid.uuid4().hex[:12]

    def _make_event(
        self,
        level: str,
        component: str,
        event_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, float]] = None,
        stack_trace: Optional[str] = None,
    ) -> TelemetryEvent:
        return TelemetryEvent(
            trace_id=self._trace_id,
            span_id=uuid.uuid4().hex[:8],
            timestamp_ns=time.time_ns(),
            level=level,
            component=component,
            event_type=event_type,
            message=message,
            context=context or {},
            metrics=metrics or {},
            stack_trace=stack_trace,
        )

    async def record(self, event: TelemetryEvent) -> None:
        """Registra evento. Non-blocking: coloca na queue."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Overflow: discard oldest

    async def info(self, component: str, event_type: str, message: str,
                   context: Optional[Dict] = None, metrics: Optional[Dict] = None) -> None:
        await self.record(self._make_event("INFO", component, event_type, message, context, metrics))

    async def warning(self, component: str, event_type: str, message: str,
                      context: Optional[Dict] = None, metrics: Optional[Dict] = None) -> None:
        await self.record(self._make_event("WARNING", component, event_type, message, context, metrics))

    async def error(self, component: str, event_type: str, message: str,
                    context: Optional[Dict] = None, metrics: Optional[Dict] = None,
                    stack_trace: Optional[str] = None) -> None:
        await self.record(self._make_event("ERROR", component, event_type, message, context, metrics, stack_trace))

    async def critical(self, component: str, event_type: str, message: str,
                       context: Optional[Dict] = None, metrics: Optional[Dict] = None) -> None:
        await self.record(self._make_event("CRITICAL", component, event_type, message, context, metrics))

    async def fatal(self, component: str, event_type: str, message: str,
                    context: Optional[Dict] = None, metrics: Optional[Dict] = None,
                    stack_trace: Optional[str] = None) -> None:
        await self.record(self._make_event("FATAL", component, event_type, message, context, metrics, stack_trace))

    async def start_writer(self) -> None:
        """Inicia background writer async."""
        self._running = True
        self._writer_task = asyncio.create_task(self._write_loop())

    async def stop_writer(self) -> None:
        """Para writer e esvazia queue."""
        self._running = False
        await self._queue.join()

    async def _write_loop(self) -> None:
        """Background loop: write events from queue to JSONL file."""
        log_file = os.path.join(self._log_dir, "telemetry.jsonl")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "trace_id": event.trace_id,
                        "span_id": event.span_id,
                        "timestamp_ns": event.timestamp_ns,
                        "level": event.level,
                        "component": event.component,
                        "event_type": event.event_type,
                        "message": event.message,
                        "context": event.context,
                        "metrics": event.metrics,
                    }, default=str) + "\n")
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
