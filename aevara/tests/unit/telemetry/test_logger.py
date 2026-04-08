# @module: aevara.tests.unit.telemetry.test_logger
# @deps: aevara.src.telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para StructuredLogger: event creation, trace propagation,
#           queue overflow, async recording.

from __future__ import annotations

import json
import pytest
import asyncio

from aevara.src.telemetry.logger import StructuredLogger, TelemetryEvent


# === HAPPY PATH ===
class TestLoggerHappyPath:
    @pytest.mark.asyncio
    async def test_record_event(self):
        logger = StructuredLogger()
        event = TelemetryEvent(
            trace_id=logger.new_trace(),
            span_id="span_001",
            timestamp_ns=0,
            level="INFO",
            component="test",
            event_type="test_event",
            message="Test message",
            context={"key": "value"},
            metrics={},
        )
        await logger.record(event)
        # Event should be in queue
        assert not logger._queue.empty()

    @pytest.mark.asyncio
    async def test_info_logs(self):
        logger = StructuredLogger()
        await logger.info("test_comp", "info_event", "Info msg", context={"x": 1})
        assert not logger._queue.empty()
        event = await logger._queue.get()
        assert event.level == "INFO"
        assert event.component == "test_comp"
        assert event.context["x"] == 1

    @pytest.mark.asyncio
    async def test_new_trace_generates_unique_ids(self):
        logger = StructuredLogger()
        t1 = logger.new_trace()
        t2 = logger.new_trace()
        assert t1 != t2

    @pytest.mark.asyncio
    async def test_error_with_stacktrace(self):
        logger = StructuredLogger()
        await logger.error("comp", "error_event", "Error", stack_trace="trace here")
        event = await logger._queue.get()
        assert event.level == "ERROR"
        assert event.stack_trace == "trace here"

    @pytest.mark.asyncio
    async def test_critical_alert(self):
        logger = StructuredLogger()
        await logger.critical("comp", "critical_event", "Critical!")
        event = await logger._queue.get()
        assert event.level == "CRITICAL"

    @pytest.mark.asyncio
    async def test_fatal_alert(self):
        logger = StructuredLogger()
        await logger.fatal("comp", "fatal_event", "System down",
                           stack_trace="full traceback")
        event = await logger._queue.get()
        assert event.level == "FATAL"


# === EDGE CASES ===
class TestLoggerEdgeCases:
    @pytest.mark.asyncio
    async def test_queue_overflow_discards(self):
        logger = StructuredLogger(queue_maxsize=5)
        for i in range(10):
            await logger.record(TelemetryEvent(
                trace_id="t1", span_id=f"s{i}", timestamp_ns=i,
                level="INFO", component="test", event_type="e", message="m",
                context={}, metrics={},
            ))
        # Queue should not be full (overflow discarded)
        assert logger._queue.qsize() <= 5

    @pytest.mark.asyncio
    async def test_empty_context_metrics(self):
        logger = StructuredLogger()
        await logger.info("comp", "event", "msg")
        event = await logger._queue.get()
        assert event.context == {}
        assert event.metrics == {}


# === ERROR CASES ===
class TestLoggerErrors:
    @pytest.mark.asyncio
    async def test_writer_file_creation(self):
        import tempfile
        import os
        logger = StructuredLogger(log_dir=tempfile.mkdtemp())
        await logger.start_writer()
        await logger.info("comp", "event", "test message")
        await asyncio.sleep(0.2)  # Give writer time
        await logger.stop_writer()
        log_files = [f for f in os.listdir(logger._log_dir) if f.endswith(".jsonl")]
        assert len(log_files) >= 1
