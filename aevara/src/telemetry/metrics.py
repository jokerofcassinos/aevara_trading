# @module: aevara.src.telemetry.metrics
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Real-time metrics collection com bounded history, composite health
#           score, e rolling window calculations.

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class MetricsCollector:
    """
    Collector de metricas em tempo real com bounded history.

    Invariantes:
    - Todas as collections tem maxlen fixo (zero vazamento)
    - Health score bounded em [0, 100]
    - Metrics query retorna None se janela vazia
    """

    max_history: int = 500

    _latencies: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _errors: deque[float] = field(default_factory=lambda: deque(maxlen=500))  # timestamp_ns
    _confidence_scores: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _alignment_scores: deque[float] = field(default_factory=lambda: deque(maxlen=500))

    def __post_init__(self):
        for attr in ["_latencies", "_errors", "_confidence_scores", "_alignment_scores"]:
            object.__setattr__(self, attr, deque(maxlen=self.max_history))

    def record_latency(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)

    def record_error(self, timestamp_ns: Optional[int] = None) -> None:
        self._errors.append(timestamp_ns or __import__("time").time_ns())

    def record_confidence(self, score: float) -> None:
        self._confidence_scores.append(max(0.0, min(1.0, score)))

    def record_alignment(self, score: float) -> None:
        self._alignment_scores.append(max(0.0, min(1.0, score)))

    def get_p50_latency(self) -> Optional[float]:
        if not self._latencies:
            return None
        return float(np.percentile(list(self._latencies), 50))

    def get_p95_latency(self) -> Optional[float]:
        if not self._latencies:
            return None
        return float(np.percentile(list(self._latencies), 95))

    def get_p99_latency(self) -> Optional[float]:
        if not self._latencies:
            return None
        return float(np.percentile(list(self._latencies), 99))

    def get_error_rate(self, window_s: float = 60.0) -> float:
        """Error rate per second in window."""
        if not self._errors:
            return 0.0
        now = __import__("time").time_ns()
        window_ns = int(window_s * 1e9)
        cutoff = now - window_ns
        count = sum(1 for ts in self._errors if ts >= cutoff)
        return count / window_s

    def get_avg_confidence(self) -> Optional[float]:
        if not self._confidence_scores:
            return None
        return sum(self._confidence_scores) / len(self._confidence_scores)

    def get_avg_alignment(self) -> Optional[float]:
        if not self._alignment_scores:
            return None
        return sum(self._alignment_scores) / len(self._alignment_scores)

    def get_health_score(self) -> float:
        """
        Health composite score [0, 100]:
        - 40% latency_score (p99 < 50ms = 100, >500ms = 0)
        - 30% error_score (rate < 0.01/s = 100, >1/s = 0)
        - 15% confidence_score (avg normalized * 100)
        - 15% alignment_score (avg normalized * 100)
        """
        p99 = self.get_p99_latency()
        latency_score = max(0.0, 100.0 - (p99 / 5.0)) if p99 else 50.0
        latency_score = min(100.0, latency_score)

        error_rate = self.get_error_rate()
        error_score = max(0.0, 100.0 - error_rate * 100.0)
        error_score = min(100.0, error_score)

        avg_conf = self.get_avg_confidence()
        conf_score = (avg_conf or 0.5) * 100.0

        avg_align = self.get_avg_alignment()
        align_score = (avg_align or 0.5) * 100.0

        health = (
            0.40 * latency_score
            + 0.30 * error_score
            + 0.15 * conf_score
            + 0.15 * align_score
        )
        return max(0.0, min(100.0, health))
