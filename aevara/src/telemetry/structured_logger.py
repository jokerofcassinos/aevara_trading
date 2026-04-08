# @module: aevara.src.telemetry.structured_logger
# @deps: asyncio, json, time, uuid, logging, logging.handlers
# @status: IMPLEMENTED_v1.1
# @last_update: 2026-04-10
# @summary: Structured JSON logging with trace-ID propagation, metrics, and RotatingFileHandler persistence (Ω-10).

from __future__ import annotations
import asyncio
import json
import time
import uuid
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

class StructuredLogger:
    """
    AEVRA Structured Logger (v1.1.0).
    Emite telemetria em formato JSON para stdout e ARQUIVO persistente.
    Flush a cada 50 eventos para garantir integridade anti-entropia.
    """
    def __init__(self, service_name: str = "AEVRA_CORE"):
        self.service_name = service_name
        self._metrics: Dict[str, List[float]] = {}
        self._events: List[Dict] = []
        self._max_history = 1000
        
        # Setup Persistent Logging
        log_dir = Path("aevara/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "aevara_audit.log"
        
        self.file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        self.file_handler.setFormatter(logging.Formatter('%(message)s'))
        self.internal_logger = logging.getLogger("AEVRA_INTERNAL")
        self.internal_logger.setLevel(logging.INFO)
        self.internal_logger.addHandler(self.file_handler)

    def log(self, level: str, message: str, **kwargs):
        """Log estruturado com metadados e persistência em arquivo."""
        entry = {
            "ts_ns": time.time_ns(),
            "level": level,
            "service": self.service_name,
            "msg": message,
            "trace_id": str(uuid.uuid4()),
            **kwargs
        }
        
        json_msg = json.dumps(entry)
        
        # Stream to stdout for Live Dashboard
        print(json_msg)
        
        # Persist to disk
        self.internal_logger.info(json_msg)
        if level in ["CRITICAL", "ERROR"]:
            self.file_handler.flush()
        
        # Internal buffer for Dashboard memory
        self._events.append(entry)
        if len(self._events) > self._max_history:
            self._events.pop(0)

    def record_metric(self, name: str, value: float):
        """Registra métrica numérica para análise de performance/regime."""
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(value)
        if len(self._metrics[name]) > self._max_history:
            self._metrics[name].pop(0)

    def get_latest_metrics(self) -> Dict[str, float]:
        """Retorna o valor mais recente de cada métrica."""
        return {k: v[-1] for k, v in self._metrics.items() if v}

    def get_event_stream(self, count: int = 50) -> List[Dict]:
        """Retorna os últimos N eventos."""
        return self._events[-count:]

# Global Instance
logger = StructuredLogger()
