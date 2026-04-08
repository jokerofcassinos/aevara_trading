# @module: aevara.tests.unit.agents.regime.test_detector
# @deps: aevara.src.agents.regime.detector
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes unitarios para regime detector.

from __future__ import annotations

import pytest
from aevara.src.agents.regime.detector import RegimeDetector, RegimeType


class TestRegimeDetectorHappyPath:
    def test_insufficient_data_returns_choppy(self):
        det = RegimeDetector(short_window=10, long_window=50)
        result = det.classify()
        assert result.regime == RegimeType.CHOPPY

    def test_classify_after_updates(self):
        det = RegimeDetector(short_window=10, long_window=50)
        for p in range(100, 200):
            det.update(p)
        result = det.classify()
        assert result.regime in (RegimeType.TRENDING, RegimeType.CRISIS)
        assert 0.0 <= result.confidence <= 1.0


class TestRegimeDetectorEdgeCases:
    def test_constant_price_is_choppy(self):
        det = RegimeDetector(short_window=10, long_window=50)
        for _ in range(60):
            det.update(100.0)
        result = det.classify()
        assert abs(result.volatility) < 1e-10


class TestRegimeDetectorSignals:
    def test_get_signal_returns_valid(self):
        det = RegimeDetector(short_window=10, long_window=50)
        for p in range(100, 105):
            det.update(p)
        signal = det.get_signal({"dummy": 0.0})
        assert -4.5 <= signal.logodds <= 4.5
        assert 0.0 <= signal.confidence <= 1.0
