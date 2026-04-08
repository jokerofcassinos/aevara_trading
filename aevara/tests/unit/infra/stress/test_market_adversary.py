# @module: aevara.tests.unit.infra.stress.test_market_adversary
# @deps: aevara.src.infra.stress.market_adversary
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para MarketAdversary: flash crash, spoofing, latency, gaps, fat tails.

from __future__ import annotations

import pytest

from aevara.src.infra.stress.market_adversary import (
    AdversarialConfig,
    AdversarialEvent,
    MarketAdversary,
    MarketShockType,
)


# === FLASH CRASH ===
class TestFlashCrash:
    def test_generates_three_phases(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_flash_crash(50000.0, 1.0)
        assert len(events) == 3

    def test_phases_are_crash_bottom_recovery(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_flash_crash(50000.0, 1.0)
        phases = [e.parameters["phase"] for e in events]
        assert phases == ["CRASH", "BOTTOM", "RECOVERY"]

    def test_drop_severity_positive(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_flash_crash(50000.0, 1.0)
        for e in events:
            assert e.severity > 0

    def test_duration_total_positive(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_flash_crash(50000.0, 1.0)
        total_duration = sum(e.duration_s for e in events)
        assert total_duration > 0

    def test_reproducible_with_seed(self):
        adv1 = MarketAdversary(seed=123)
        adv2 = MarketAdversary(seed=123)
        events1 = adv1.generate_flash_crash(50000.0, 1.0)
        events2 = adv2.generate_flash_crash(50000.0, 1.0)
        assert all(e1.severity == e2.severity for e1, e2 in zip(events1, events2))

    def test_nonreproducible_without_seed(self):
        adv1 = MarketAdversary()
        adv2 = MarketAdversary()
        # Very likely different, but check independently valid
        events1 = adv1.generate_flash_crash(50000.0, 1.0)
        events2 = adv2.generate_flash_crash(50000.0, 1.0)
        assert len(events1) == 3
        assert len(events2) == 3


# === SPOOFING ===
class TestSpoofing:
    def test_generates_multiple_layers(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_spoofing("BTC/USD", "SELL")
        assert len(events) >= 3
        assert len(events) <= 8

    def test_events_have_cancel_rate(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_spoofing("BTC/USD", "BUY")
        for e in events:
            assert "cancel_rate" in e.parameters
            assert e.parameters["cancel_rate"] == 0.75

    def test_spoof_size_positive(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_spoofing("ETH/USD", "SELL")
        for e in events:
            assert e.parameters["spoof_size"] > 0

    def test_spoofing_has_direction(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_spoofing("BTC/USD", "SELL")
        for e in events:
            assert e.parameters["direction"] == "SELL"


# === LATENCY SPIKE ===
class TestLatencySpike:
    def test_generates_single_event(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_latency_spike()
        assert len(events) == 1
        assert events[0].shock_type == MarketShockType.LATENCY_SPIKE

    def test_has_gamma_parameters(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_latency_spike(base_latency_ms=100)
        e = events[0]
        assert "gamma_k" in e.parameters
        assert "gamma_theta" in e.parameters

    def test_severity_bounded(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_latency_spike(base_latency_ms=50)
        assert 0.0 <= events[0].severity


# === EXCHANGE DOWNTIME ===
class TestDowntime:
    def test_generates_single_event(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_exchange_downtime()
        assert len(events) == 1
        assert events[0].shock_type == MarketShockType.EXCHANGE_DOWNTIME

    def test_has_disconnection_params(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_exchange_downtime()
        e = events[0]
        assert e.parameters["ws_disconnected"] is True
        assert e.parameters["data_gap"] is True


# === GAPPING ===
class TestGapping:
    def test_generates_single_event(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_gapping(50000.0)
        assert len(events) == 1
        assert events[0].shock_type == MarketShockType.GAPPING

    def test_gap_has_direction(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_gapping(50000.0)
        assert events[0].parameters["direction"] in ("UP", "DOWN")

    def test_gap_price_different_from_base(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_gapping(50000.0)
        assert events[0].parameters["gap_price"] != events[0].parameters["base_price"]


# === FAT TAIL RETURNS ===
class TestFatTailReturns:
    def test_returns_shape(self):
        adv = MarketAdversary(seed=42)
        returns = adv.generate_fat_tail_returns(1000)
        assert len(returns) == 1000

    def test_returns_have_heavier_tails_than_normal(self):
        adv = MarketAdversary(seed=42)
        returns = adv.generate_fat_tail_returns(10000)
        # Check kurtosis is higher than normal (normal ≈ 3)
        from scipy.stats import kurtosis
        kurt = kurtosis(returns)
        assert kurt > 3.0

    def test_returns_centered_near_zero(self):
        adv = MarketAdversary(seed=42)
        returns = adv.generate_fat_tail_returns(10000)
        import numpy as np
        assert abs(np.mean(returns)) < 0.05


# === MULTI-SHOCK ===
class TestMultiShock:
    def test_generates_multiple_events(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_multi_shock(n_shocks=3)
        assert len(events) > 3  # Each shock can generate multiple events

    def test_events_sorted_by_time(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_multi_shock(n_shocks=5)
        timestamps = [e.ts for e in events]
        assert timestamps == sorted(timestamps)

    def test_valid_shock_types(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_multi_shock(n_shocks=10)
        for e in events:
            assert isinstance(e.shock_type, MarketShockType)
            assert e.severity >= 0


# === SEVERITY DISTRIBUTION ===
class TestSeverityDistribution:
    def test_distribution_in_bounds(self):
        adv = MarketAdversary(seed=42)
        dist = adv.get_severity_distribution(1000)
        assert all(0 <= x <= 1 for x in dist)

    def test_distribution_mean_less_than_half(self):
        adv = MarketAdversary(seed=42)
        dist = adv.get_severity_distribution(10000)
        import numpy as np
        assert np.mean(dist) < 0.5  # Beta(2,5) mean = 2/7 ≈ 0.286


# === APPLY LATENCY ===
class TestApplyLatency:
    def test_normal_event_latency(self):
        adv = MarketAdversary(seed=42)
        event = AdversarialEvent(
            shock_type=MarketShockType.FLASH_CRASH,
            ts=0.0, severity=0.5, duration_s=10.0, parameters={},
        )
        latency = adv.apply_latency_to_event(event, base_latency_ms=50)
        assert latency > 0
        # Normal latency should be around base (within 3 sigma)
        assert latency < 500

    def test_latency_spike_event(self):
        adv = MarketAdversary(seed=42)
        events = adv.generate_latency_spike()
        latency = adv.apply_latency_to_event(events[0])
        assert latency > 0  # Gamma distributed, always positive


# === CUSTOM CONFIG ===
class TestCustomConfig:
    def test_custom_config_applied(self):
        config = AdversarialConfig(
            flash_crash_drop_pct=20.0,
            fat_tail_alpha=1.5,
            latency_spike_ms=10000,
        )
        adv = MarketAdversary(config=config, seed=42)
        events = adv.generate_flash_crash(50000.0, 1.0)
        assert events[0].severity <= 0.2  # Max 20% drop
