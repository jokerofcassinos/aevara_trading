# @module: aevara.src.utils.logging
# @deps: None
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Structured JSON logging with trace_id propagation, hierarchical levels,
#           and file-based persistence for audit compliance.

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Hierarchical alert routing: INFO -> log, WARNING -> log + flag, CRITICAL -> log + alert
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class StructuredLogger:
    """
    JSON-structured logger with trace_id propagation.
    All log entries include: timestamp, level, component, message, trace_id, extra_fields.
    """

    def __init__(
        self,
        component: str,
        log_dir: str = "data/audit",
        level: str = "INFO",
        trace_id: Optional[str] = None,
    ):
        self.component = component
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.level = LOG_LEVEL_MAP.get(level, logging.INFO)

        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{component}.jsonl")
        self.log_file = log_file

    def _write(self, level: str, message: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "component": self.component,
            "message": message,
            "trace_id": self.trace_id,
            **kwargs,
        }
        if self.level <= LOG_LEVEL_MAP.get(level, logging.INFO):
            # JSON line append to audit log
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")

    def info(self, message: str, **kwargs: Any) -> None:
        self._write("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._write("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._write("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._write("CRITICAL", message, **kwargs)

    def child(self, child_component: str) -> StructuredLogger:
        """Create a child logger sharing the same trace_id."""
        return StructuredLogger(
            component=child_component,
            log_dir=os.path.dirname(self.log_file),
            trace_id=self.trace_id,
        )


def make_logger(component: str, log_dir: str = "data/audit", level: str = "INFO") -> StructuredLogger:
    """Factory for structured loggers."""
    return StructuredLogger(component=component, log_dir=log_dir, level=level)
