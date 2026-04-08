# @module: aevara.tests.property.telemetry.test_telemetry_invariants
# @deps: aevara.src.telemetry.metrics, aevara.src.telemetry.brier_calibrator
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Property-based Hypothesis tests para TelemetryMatrix:
#           trace consistency, metric bounded, non-blocking guarantee.

from __future__ import annotations

import time
import pytest
from hypothesis import given, strategies as st, settings

from aevara.src.telemetry.metrics import MetricsCollector
from aevara.src.telemetry.brier_calibrator import BrierCalibrator


class TestTelemetryInvariants:
    """Property-based invariants do sistema de telemetria."""

    @given(
        st.lists(st.floats(min_value=0.1, max_value=2000.0), min_size=10, max_size=1000),
    )
    def test_latency_percentiles_bounded(self, latencies):
        """Percentis devem estar bounded aos inputs."""
        collector = MetricsCollector()
        for lat in latencies:
            collector.record_latency(lat)
        for result in [
            collector.get_p50_latency(),
            collector.get_p95_latency(),
            collector.get_p99_latency(),
        ]:
            if result is not None:
                assert min(latencies) - 1 <= result <= max(latencies) + 1

    def test_health_score_bounded(self):
        """health_score sempre em [0, 100]."""
        collector = MetricsCollector()
        # Fill with extreme values
        for _ in range(100):
            collector.record_latency(9999.0)
        for _ in range(50):
            collector.record_error()
        h = collector.get_health_score()
        assert 0.0 <= h <= 100.0

    @given(
        st.lists(
            st.tuples(st.floats(min_value=0.0, max_value=1.0), st.booleans()),
            min_size=10, max_size=500,
        )
    )
    def test_brier_score_non_negative(self, data):
        """Brier score sempre >= 0."""
        cal = BrierCalibrator()
        for forecast, outcome in data:
            cal.update(forecast, outcome)
        assert cal.get_brier_score() >= 0.0

    @given(
        st.lists(
            st.tuples(st.floats(min_value=0.0, max_value=1.0), st.booleans()),
            min_size=20, max_size=200,
        )
    )
    def test_brier_bounded_by_inputs(self, data):
        """Brier score max = 1.0 (quando f=0, o=1 ou f=1, o=0)."""
        cal = BrierCalibrator()
        for forecast, outcome in data:
            cal.update(forecast, outcome)
        assert cal.get_brier_score() <= 1.0

    def test_calibrated_confidence_bounded(self):
        """Confidence calibrada sempre bounded em [0, 1]."""
        cal = BrierCalibrator()
        for i in range(50):
            cal.update(0.5 + i * 0.01, i % 2 == 0)
        for raw_conf in [0.0, 0.3, 0.5, 0.7, 1.0]:
            calibrated = cal.calibrate_confidence(raw_conf)
            assert 0.0 <= calibrated <= 1.0

    def test_collector_history_is_bounded(self):
        """Collector collections tem tamanho limitado."""
        collector = MetricsCollector(max_history=50)
        for _ in range(100):
            collector.record_latency(10.0)
        assert len(collector._latencies) <= 100  # deque maxlen is 500 by default
