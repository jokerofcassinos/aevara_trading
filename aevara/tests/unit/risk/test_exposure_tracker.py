# @module: aevara.tests.unit.risk.test_exposure_tracker
# @deps: aevara.src.risk.exposure_tracker
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para ExposureTracker: posicoes, limites, net/gross, concentration.

from __future__ import annotations

import time

import pytest

from aevara.src.risk.exposure_tracker import (
    ExposureSnapshot,
    ExposureTracker,
    PositionExposure,
    PositionSide,
)


NOW = time.time()


# === ADD POSITION ===
class TestAddPosition:
    def test_add_long(self):
        tracker = ExposureTracker()
        success, reason = tracker.add_position("BTC/USD", PositionSide.LONG, 5.0, 50000.0, NOW)
        assert success
        assert reason == ""
        assert tracker.position_count() == 1

    def test_add_short(self):
        tracker = ExposureTracker()
        success, _ = tracker.add_position("ETH/USD", PositionSide.SHORT, 3.0, 3000.0, NOW)
        assert success
        assert tracker.position_count() == 1

    def test_negative_notional_rejected(self):
        tracker = ExposureTracker()
        success, reason = tracker.add_position("BTC/USD", PositionSide.LONG, -1.0, 50000.0, NOW)
        assert not success
        assert "positive" in reason.lower()

    def test_duplicate_symbol_rejected(self):
        tracker = ExposureTracker()
        tracker.add_position("BTC/USD", PositionSide.LONG, 5.0, 50000.0, NOW)
        success, reason = tracker.add_position("BTC/USD", PositionSide.LONG, 3.0, 51000.0, NOW)
        assert not success
        assert "already exists" in reason.lower()

    def test_max_positions_rejected(self):
        tracker = ExposureTracker(max_positions=2, max_gross_pct=1000.0, max_net_pct=1000.0)
        tracker.add_position("A", PositionSide.LONG, 1.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 1.0, 1.0, NOW)
        success, reason = tracker.add_position("C", PositionSide.LONG, 1.0, 1.0, NOW)
        assert not success
        assert "max positions" in reason.lower()

    def test_single_position_limit(self):
        tracker = ExposureTracker(max_single_pct=10.0)
        success, reason = tracker.add_position("BTC/USD", PositionSide.LONG, 15.0, 50000.0, NOW)
        assert not success
        assert "exceeds max" in reason.lower()


# === GROSS / NET EXPOSURE ===
class TestGrossNetExposure:
    def test_gross_calculation(self):
        tracker = ExposureTracker(max_gross_pct=50.0)
        tracker.add_position("A", PositionSide.LONG, 3.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.SHORT, 2.0, 1.0, NOW)
        snap = tracker.get_snapshot()
        assert snap.gross_exposure_pct == 5.0

    def test_net_calculation(self):
        tracker = ExposureTracker(max_gross_pct=200.0, max_net_pct=100.0)
        tracker.add_position("A", PositionSide.LONG, 8.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 2.0, 1.0, NOW)
        tracker.add_position("C", PositionSide.SHORT, 5.0, 1.0, NOW)
        snap = tracker.get_snapshot()
        assert snap.net_exposure_pct == 5.0  # 10 - 5

    def test_long_and_short_totals(self):
        tracker = ExposureTracker(max_gross_pct=200.0, max_net_pct=100.0)
        tracker.add_position("A", PositionSide.LONG, 4.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 6.0, 1.0, NOW)
        tracker.add_position("C", PositionSide.SHORT, 3.0, 1.0, NOW)
        snap = tracker.get_snapshot()
        assert snap.long_exposure_pct == 10.0
        assert snap.short_exposure_pct == 3.0

    def test_gross_exposure_limit(self):
        tracker = ExposureTracker(max_gross_pct=10.0, max_net_pct=100.0, max_single_pct=15.0)
        tracker.add_position("A", PositionSide.LONG, 5.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 5.0, 1.0, NOW)
        success, reason = tracker.add_position("C", PositionSide.SHORT, 3.0, 1.0, NOW)
        assert not success
        assert "gross" in reason.lower()

    def test_net_exposure_limit_long(self):
        tracker = ExposureTracker(max_gross_pct=1000.0, max_net_pct=8.0, max_single_pct=15.0)
        tracker.add_position("A", PositionSide.LONG, 5.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 3.0, 1.0, NOW)
        success, reason = tracker.add_position("C", PositionSide.LONG, 5.0, 1.0, NOW)
        assert not success
        assert "net" in reason.lower()


# === POSITION MANAGEMENT ===
class TestPositionManagement:
    def test_remove_position(self):
        tracker = ExposureTracker()
        tracker.add_position("A", PositionSide.LONG, 5.0, 1.0, NOW)
        assert tracker.remove_position("A")
        assert tracker.position_count() == 0

    def test_remove_nonexistent(self):
        tracker = ExposureTracker()
        assert not tracker.remove_position("nonexistent")

    def test_update_position(self):
        tracker = ExposureTracker(max_single_pct=20.0)
        tracker.add_position("A", PositionSide.LONG, 5.0, 50000.0, NOW)
        success, _ = tracker.update_position("A", 8.0)
        assert success
        pos = tracker.get_position("A")
        assert pos is not None
        assert pos.notional_pct == 8.0
        assert pos.entry_price == 50000.0  # Preserved
        assert pos.entry_ts == NOW

    def test_update_nonexistent(self):
        tracker = ExposureTracker()
        success, reason = tracker.update_position("X", 5.0)
        assert not success

    def test_update_exceeds_single_limit(self):
        tracker = ExposureTracker(max_single_pct=10.0)
        tracker.add_position("A", PositionSide.LONG, 5.0, 50000.0, NOW)
        success, _ = tracker.update_position("A", 15.0)
        assert not success

    def test_update_exceeds_gross(self):
        tracker = ExposureTracker(max_gross_pct=20.0, max_single_pct=50.0)
        tracker.add_position("A", PositionSide.LONG, 15.0, 50000.0, NOW)
        success, reason = tracker.update_position("A", 25.0)
        assert not success

    def test_get_all_positions(self):
        tracker = ExposureTracker()
        tracker.add_position("A", PositionSide.LONG, 3.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.SHORT, 2.0, 1.0, NOW)
        positions = tracker.get_all_positions()
        assert set(positions.keys()) == {"A", "B"}

    def test_get_position(self):
        tracker = ExposureTracker()
        tracker.add_position("A", PositionSide.LONG, 3.0, 1.0, NOW)
        pos = tracker.get_position("A")
        assert pos is not None
        assert pos.symbol == "A"
        assert pos.side == PositionSide.LONG

    def test_clear(self):
        tracker = ExposureTracker()
        tracker.add_position("A", PositionSide.LONG, 3.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.SHORT, 2.0, 1.0, NOW)
        tracker.clear()
        assert tracker.position_count() == 0


# === SNAPSHOT ===
class TestSnapshot:
    def test_empty_snapshot(self):
        tracker = ExposureTracker()
        snap = tracker.get_snapshot()
        assert snap.gross_exposure_pct == 0.0
        assert snap.net_exposure_pct == 0.0
        assert snap.position_count == 0
        assert snap.largest_position_pct == 0.0
        assert snap.concentration_ratio == 0.0
        assert snap.is_within_limits

    def test_concentration_ratio(self):
        tracker = ExposureTracker(max_gross_pct=1000.0, max_net_pct=100.0)
        tracker.add_position("A", PositionSide.LONG, 5.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.LONG, 5.0, 1.0, NOW)
        snap = tracker.get_snapshot()
        assert snap.largest_position_pct == 5.0
        assert snap.concentration_ratio == pytest.approx(0.5, abs=0.01)


# === EDGE CASES ===
class TestEdgeCases:
    def test_invalid_max_positions(self):
        with pytest.raises(AssertionError):
            ExposureTracker(max_positions=0)

    def test_invalid_gross(self):
        with pytest.raises(AssertionError):
            ExposureTracker(max_gross_pct=0)

    def test_balanced_long_short(self):
        tracker = ExposureTracker(max_gross_pct=200.0, max_net_pct=100.0, max_single_pct=50.0)
        tracker.add_position("A", PositionSide.LONG, 10.0, 1.0, NOW)
        tracker.add_position("B", PositionSide.SHORT, 10.0, 1.0, NOW)
        snap = tracker.get_snapshot()
        assert snap.net_exposure_pct == 0.0
        assert snap.gross_exposure_pct == 20.0
        assert snap.is_within_limits
