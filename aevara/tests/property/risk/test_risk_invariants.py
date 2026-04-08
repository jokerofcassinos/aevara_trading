# @module: aevara.tests.property.risk.test_risk_invariants
# @deps: aevara.src.risk.*, hypothesis, pytest
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Property-based tests para invariantes de risco: sizing bounds,
#           Kelly bounded, drawdown monotonic, exposure limits.

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from aevara.src.risk.risk_engine import RiskConfig, RiskEngine, VetoReason
from aevara.src.risk.position_sizing import PositionSizer, SizingConfig
from aevara.src.risk.exposure_tracker import ExposureTracker, PositionSide


# === SIZING BOUNDS ===
class TestSizingInvariants:
    @given(
        st.floats(0.0, 1.0),  # win_rate
        st.floats(0.01, 10.0),  # avg_win
        st.floats(0.01, 10.0),  # avg_loss
        st.floats(0.01, 100.0),  # vol
        st.floats(0.0, 1.0),  # risk_cap
    )
    @settings(max_examples=200)
    def test_position_never_negative(self, win_rate, avg_win, avg_loss, vol, risk_cap):
        sizer = PositionSizer()
        result = sizer.calculate_position(
            win_rate=win_rate, avg_win_pct=avg_win, avg_loss_pct=avg_loss,
            current_vol_pct=vol, risk_cap=risk_cap
        )
        assert result.notional_pct >= 0.0

    @given(
        st.floats(0.51, 0.99),
        st.floats(0.5, 10.0),
        st.floats(0.1, 5.0),
        st.floats(5.0, 50.0),
    )
    @settings(max_examples=200)
    def test_position_never_exceeds_max(self, win_rate, avg_win, avg_loss, vol):
        sizer = PositionSizer(config=SizingConfig(max_position_pct=10.0))
        result = sizer.calculate_position(
            win_rate=win_rate, avg_win_pct=avg_win, avg_loss_pct=avg_loss,
            current_vol_pct=vol, risk_cap=1.0
        )
        assert result.notional_pct <= 10.0

    @given(
        st.floats(0.0, 1.0),
        st.floats(0.01, 5.0),
        st.floats(0.01, 5.0),
    )
    @settings(max_examples=200)
    def test_kelly_raw_bounded(self, win_rate, avg_win, avg_loss):
        kelly = PositionSizer.kelly_criterion(win_rate, avg_win, avg_loss)
        assert 0.0 <= kelly <= 1.0


# === RISK ENGINE ===
class TestRiskEngineInvariants:
    @given(
        st.floats(0.0, 1.0),  # signal_confidence
        st.booleans(),  # regime_hostile
        st.floats(0.0, 50.0),  # proposed_notional
        st.floats(0.0, 9.0),  # drawdown (keep below max to test soft zone)
    )
    @settings(max_examples=200)
    def test_cap_in_bounds(self, signal_confidence, regime, notional, drawdown):
        config = RiskConfig(max_drawdown_pct=10.0, soft_drawdown_pct=2.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(100.0 * (1 - drawdown / 100.0))
        assessment = engine.assess_risk(signal_confidence, regime, notional)
        assert 0.0 <= assessment.position_cap <= 1.0
        assert assessment.is_blocked == (assessment.position_cap == 0.0)


# === EXPOSURE ===
class TestExposureInvariants:
    @given(
        st.floats(0.1, 10.0),
        st.floats(0.1, 10.0),
        st.floats(0.1, 10.0),
    )
    @settings(max_examples=200)
    def test_gross_geq_net(self, n1, n2, n3):
        tracker = ExposureTracker(max_gross_pct=50.0, max_net_pct=50.0)
        tracker.add_position("A", PositionSide.LONG, n1, 1.0, 0.0)
        # Add second as short to create net < gross
        success2, _ = tracker.add_position("B", PositionSide.SHORT, min(n2, 50.0 - tracker.get_snapshot().gross_exposure_pct), 1.0, 0.0)
        if success2:
            snap = tracker.get_snapshot()
            assert snap.gross_exposure_pct >= abs(snap.net_exposure_pct)
        # Try adding a third
        tracker.add_position("C", PositionSide.LONG, min(n3, 1.0), 1.0, 0.0)
        snap2 = tracker.get_snapshot()
        assert snap2.gross_exposure_pct >= abs(snap2.net_exposure_pct)

    @given(st.integers(1, 50))
    @settings(max_examples=100)
    def test_gross_is_sum_of_pos(self, max_pos):
        tracker = ExposureTracker(max_gross_pct=999.0, max_net_pct=999.0, max_positions=max_pos)
        for i in range(max_pos):
            success, _ = tracker.add_position(f"A{i}", PositionSide.LONG, 1.0, 1.0, 0.0)
            if not success:
                break
        snap = tracker.get_snapshot()
        assert abs(snap.gross_exposure_pct - snap.position_count * 1.0) < 0.001

    @given(st.data())
    @settings(max_examples=50)
    def test_concentration_ratio_valid(self, data):
        num_positions = data.draw(st.integers(1, 10))
        tracker = ExposureTracker(max_gross_pct=1000.0, max_net_pct=1000.0)
        for i in range(num_positions):
            size = data.draw(st.floats(0.5, 5.0))
            tracker.add_position(f"A{i}", PositionSide.LONG, size, 1.0, 0.0)
        snap = tracker.get_snapshot()
        assert snap.concentration_ratio >= 0.0
        assert snap.concentration_ratio <= 1.0
        if snap.position_count == 1:
            assert snap.concentration_ratio == 1.0
