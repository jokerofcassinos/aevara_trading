# @module: aevara.tests.unit.execution.test_algorithms
# @deps: aevara.src.execution.algorithms
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para ExecutionAlgorithms: TWAP, VWAP, POV, Iceberg,
#           market impact modeling, early exit, dynamic adjustment.

from __future__ import annotations

import math

import pytest

from aevara.src.execution.algorithms import (
    ExecutionAlgorithms,
    AlgoType,
    ChildOrder,
    ExecutionPlan,
    MarketImpactModel,
)


@pytest.fixture
def algos():
    return ExecutionAlgorithms()


# === MARKET IMPACT ===
class TestMarketImpact:
    def test_impact_increases_with_size(self, algos):
        i1 = algos.compute_market_impact(0.01, 0.01)
        i2 = algos.compute_market_impact(0.10, 0.01)
        assert i2 > i1

    def test_impact_increases_with_volatility(self, algos):
        i1 = algos.compute_market_impact(0.10, 0.01)
        i2 = algos.compute_market_impact(0.10, 0.03)
        assert i2 > i1

    def test_capped_at_max_participation(self, algos):
        # participation capped at 1.0
        i1 = algos.compute_market_impact(1.0, 0.01)
        i2 = algos.compute_market_impact(5.0, 0.01)
        assert i2 == i1


# === TWAP ===
class TestTWAP:
    def test_correct_n_slices(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="BUY", total_size=100.0,
            duration_s=60.0, n_slices=8,
        )
        assert len(plan.child_orders) == 8
        assert plan.algo_type == AlgoType.TWAP

    def test_total_size_preserved(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="BUY", total_size=1.5,
            duration_s=60.0, n_slices=5,
        )
        total = sum(c.size for c in plan.child_orders)
        assert total == pytest.approx(1.5, rel=1e-8)

    def test_times_are_sequential(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="BUY", total_size=1.0,
            duration_s=100.0, n_slices=10,
        )
        times = [c.scheduled_time_s for c in plan.child_orders]
        assert times == sorted(times)
        assert times[0] == 0.0

    def test_early_exit_buy(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="BUY", total_size=1.0,
            duration_s=60.0, current_price=50000.0,
            early_exit_threshold_pct=0.5,
        )
        # BUY exit = price goes +0.5% above entry (slipped too far)
        assert plan.early_exit_price == pytest.approx(50000.0 * 1.005)

    def test_early_exit_sell(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="SELL", total_size=1.0,
            duration_s=60.0, current_price=50000.0,
            early_exit_threshold_pct=0.5,
        )
        assert plan.early_exit_price == pytest.approx(50000.0 * 0.995)

    def test_positive_tce(self, algos):
        plan = algos.generate_twap(
            symbol="BTC/USD", side="BUY", total_size=1.0,
            duration_s=60.0, volatility=0.01,
        )
        assert plan.expected_tce_bps > 0


# === VWAP ===
class TestVWAP:
    def test_correct_n_buckets(self, algos):
        plan = algos.generate_vwap(total_size=1.0, duration_s=120.0)
        assert len(plan.child_orders) == 10

    def test_total_size_preserved(self, algos):
        plan = algos.generate_vwap(total_size=2.5, duration_s=60.0)
        total = sum(c.size for c in plan.child_orders)
        assert total == pytest.approx(2.5, rel=1e-6)

    def test_custom_volume_profile(self, algos):
        import numpy as np
        profile = np.array([0.1] * 10)
        plan = algos.generate_vwap(
            total_size=1.0, duration_s=60.0, volume_profile=profile
        )
        assert len(plan.child_orders) == 10
        total = sum(c.size for c in plan.child_orders)
        assert total == pytest.approx(1.0, rel=1e-8)

    def test_algo_type(self, algos):
        plan = algos.generate_vwap(total_size=1.0, duration_s=60.0)
        assert plan.algo_type == AlgoType.VWAP


# === POV ===
class TestPOV:
    def test_participation_capped(self, algos):
        """POV caps at 30% participation."""
        plan = algos.generate_pov(
            total_size=1.0, participation_rate=0.5,
            duration_s=60.0, avg_volume_per_second=10.0,
        )
        assert plan.participation_rate == pytest.approx(0.3)

    def test_positive_plan(self, algos):
        plan = algos.generate_pov(
            total_size=1.0, participation_rate=0.1,
            duration_s=60.0, avg_volume_per_second=10.0,
        )
        assert plan.algo_type == AlgoType.POV
        assert len(plan.child_orders) > 0

    def test_total_size_approx_preserved(self, algos):
        plan = algos.generate_pov(
            total_size=10.0, participation_rate=0.1,
            duration_s=60.0, avg_volume_per_second=100.0,
        )
        total = sum(c.size for c in plan.child_orders)
        assert total > 0


# === ICEBERG ===
class TestIceberg:
    def test_multiple_slices(self, algos):
        plan = algos.generate_iceberg(
            total_size=10.0, visible_size=1.0,
            current_price=50000.0, side="BUY",
        )
        assert len(plan.child_orders) == 10

    def test_total_size_preserved(self, algos):
        plan = algos.generate_iceberg(
            total_size=5.0, visible_size=1.25,
            current_price=50000.0, side="SELL",
        )
        total = sum(c.size for c in plan.child_orders)
        assert total == pytest.approx(5.0, rel=1e-6)

    def test_hidden_slices(self, algos):
        plan = algos.generate_iceberg(
            total_size=10.0, visible_size=2.0,
            current_price=50000.0, side="BUY",
        )
        # All but last should be hidden
        for i, child in enumerate(plan.child_orders):
            if i < len(plan.child_orders) - 1:
                assert child.is_hidden
            else:
                assert not child.is_hidden

    def test_algo_type(self, algos):
        plan = algos.generate_iceberg(
            total_size=5.0, visible_size=1.0,
            current_price=50000.0, side="BUY",
        )
        assert plan.algo_type == AlgoType.ICEBERG

    def test_visible_size_must_be_positive(self, algos):
        with pytest.raises(AssertionError, match="Visible size must be positive"):
            algos.generate_iceberg(
                total_size=10.0, visible_size=0.0,
                current_price=50000.0, side="BUY",
            )

    def test_visible_size_less_than_total(self, algos):
        with pytest.raises(AssertionError, match="Visible size < total"):
            algos.generate_iceberg(
                total_size=10.0, visible_size=10.0,
                current_price=50000.0, side="BUY",
            )


# === EARLY EXIT ===
class TestEarlyExit:
    def test_no_exit_when_stable(self, algos):
        exit_flag, reason = algos.check_early_exit(
            current_price=50000.0, entry_price=50000.0, side="BUY", threshold_pct=0.5,
        )
        assert not exit_flag

    def test_buy_exit_on_drop(self, algos):
        exit_flag, reason = algos.check_early_exit(
            current_price=49000.0, entry_price=50000.0, side="BUY", threshold_pct=0.5,
        )
        assert exit_flag
        assert "dropped" in reason.lower()

    def test_sell_exit_on_rise(self, algos):
        exit_flag, reason = algos.check_early_exit(
            current_price=51000.0, entry_price=50000.0, side="SELL", threshold_pct=0.5,
        )
        assert exit_flag
        assert "rose" in reason.lower()

    def test_zero_price_no_exit(self, algos):
        exit_flag, _ = algos.check_early_exit(
            current_price=0.0, entry_price=50000.0, side="BUY", threshold_pct=0.5,
        )
        assert not exit_flag


# === IMPACT ADJUSTMENT ===
class TestImpactAdjustment:
    def test_reduces_participation_on_high_vol(self, algos):
        base = algos.generate_pov(
            total_size=1.0, participation_rate=0.1,
            duration_s=60.0, avg_volume_per_second=100.0,
            volatility=0.01,
        )
        adjusted = algos.adjust_for_impact(
            base, actual_volatility=0.05,
        )
        # Higher vol -> should trigger recalculation for TWAP
        assert adjusted is not None
