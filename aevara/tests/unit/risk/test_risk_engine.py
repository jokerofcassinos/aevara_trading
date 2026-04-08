# @module: aevara.tests.unit.risk.test_risk_engine
# @deps: aevara.src.risk.risk_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para RiskEngine: drawdown circuit breaker, vetos, vol tracking, equity updates.

from __future__ import annotations

import pytest

from aevara.src.risk.risk_engine import (
    RiskAssessment,
    RiskConfig,
    RiskEngine,
    VetoReason,
)


# === DRAWDOWN ===
class TestDrawdownCircuitBreaker:
    def test_no_drawdown_initially(self):
        engine = RiskEngine()
        assert engine.current_drawdown_pct == 0.0

    def test_drawdown_on_equity_drop(self):
        engine = RiskEngine()
        engine.update_equity(100.0)
        engine.update_equity(95.0)
        assert engine.current_drawdown_pct == pytest.approx(5.0, abs=0.01)

    def test_peak_tracks_max(self):
        engine = RiskEngine()
        engine.update_equity(100.0)
        engine.update_equity(110.0)
        engine.update_equity(105.0)
        # Peak is 110, current is 105
        assert engine.current_drawdown_pct == pytest.approx(4.545, abs=0.01)

    def test_hard_drawdown_blocks(self):
        config = RiskConfig(max_drawdown_pct=5.0, soft_drawdown_pct=3.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(94.0)  # 6% drawdown
        assessment = engine.assess_risk()
        assert assessment.is_blocked
        assert VetoReason.DRAWDOWN_LIMIT in assessment.vetos
        assert assessment.position_cap == 0.0

    def test_soft_drawdown_reduces_cap(self):
        config = RiskConfig(max_drawdown_pct=10.0, soft_drawdown_pct=3.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(95.0)  # 5% drawdown (between soft and hard)
        assessment = engine.assess_risk()
        assert not assessment.is_blocked
        assert assessment.position_cap < 1.0

    def test_hard_drawdown_at_exact_limit(self):
        config = RiskConfig(max_drawdown_pct=5.0, soft_drawdown_pct=3.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(95.0)  # Exactly 5% drawdown
        assessment = engine.assess_risk()
        assert assessment.is_blocked
        assert assessment.position_cap == 0.0


# === CIRCUIT BREAKER (CONSECUTIVE LOSSES) ===
class TestConsecutiveLossesCircuitBreaker:
    def test_circuit_opens_after_max_losses(self):
        config = RiskConfig(max_consecutive_losses=3)
        engine = RiskEngine(config=config)
        engine.record_loss()
        engine.record_loss()
        assert not engine.is_circuit_open
        engine.record_loss()
        assert engine.is_circuit_open

    def test_circuit_blocked_assessment(self):
        config = RiskConfig(max_consecutive_losses=3)
        engine = RiskEngine(config=config)
        for _ in range(3):
            engine.record_loss()
        assessment = engine.assess_risk()
        assert assessment.is_blocked
        assert VetoReason.CIRCUIT_BREAKER in assessment.vetos
        assert assessment.position_cap == 0.0

    def test_gain_resets_circuit(self):
        config = RiskConfig(max_consecutive_losses=3)
        engine = RiskEngine(config=config)
        engine.record_loss()
        engine.record_loss()
        engine.record_gain()
        engine.record_loss()
        assert not engine.is_circuit_open

    def test_gain_resets_counter(self):
        config = RiskConfig(max_consecutive_losses=3)
        engine = RiskEngine(config=config)
        engine.record_loss()
        engine.record_loss()
        engine.record_gain()
        engine.record_loss()
        engine.record_loss()
        engine.record_loss()  # 3rd after reset
        assert engine.is_circuit_open

    def test_reset_after_circuit(self):
        config = RiskConfig(max_consecutive_losses=3)
        engine = RiskEngine(config=config)
        for _ in range(3):
            engine.record_loss()
        assert engine.is_circuit_open
        engine.reset()
        assert not engine.is_circuit_open


# === SIGNAL CONFIDENCE ===
class TestSignalConfidence:
    def test_low_confidence_reduces_cap(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.2)
        assert not assessment.is_blocked
        assert assessment.position_cap < 1.0
        assert VetoReason.LOW_CONFIDENCE in assessment.vetos

    def test_high_confidence_no_reduction(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.8)
        assert assessment.position_cap == 1.0
        assert not assessment.is_blocked

    def test_zero_confidence(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.0)
        assert assessment.position_cap == 0.0
        assert VetoReason.LOW_CONFIDENCE in assessment.vetos


# === REGIME HOSTILE ===
class TestRegimeHostile:
    def test_hostile_regime_blocks_low_confidence(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.2, regime_hostile=True)
        assert assessment.is_blocked
        assert VetoReason.REGIME_HOSTILE in assessment.vetos

    def test_hostile_regime_allows_high_confidence(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.7, regime_hostile=True)
        assert not assessment.is_blocked

    def test_normal_regime_low_confidence_not_blocked(self):
        engine = RiskEngine()
        assessment = engine.assess_risk(signal_confidence=0.2, regime_hostile=False)
        # Low confidence reduces cap but doesn't fully block
        assert assessment.position_cap == pytest.approx(0.2 / 0.3, abs=0.01)


# === HIGH VOLATILITY ===
class TestHighVolatility:
    def test_high_vol_reduces_cap(self):
        config = RiskConfig(vol_target_pct=15.0)
        engine = RiskEngine(config=config)
        for _ in range(30):
            engine.record_vol(50.0)  # Way above 2*15=30 target
        assessment = engine.assess_risk()
        assert VetoReason.HIGH_VOLATILITY in assessment.vetos
        assert assessment.position_cap < 1.0

    def test_normal_vol_no_reduction(self):
        config = RiskConfig(vol_target_pct=15.0)
        engine = RiskEngine(config=config)
        for _ in range(10):
            engine.record_vol(10.0)
        assessment = engine.assess_risk()
        assert VetoReason.HIGH_VOLATILITY not in assessment.vetos

    def test_vol_empty_returns_zero(self):
        engine = RiskEngine()
        assert engine.current_vol_pct == 0.0


# === EXPOSURE CAP ===
class TestExposureCap:
    def test_proposed_exceeds_max(self):
        config = RiskConfig(max_position_pct=10.0)
        engine = RiskEngine(config=config)
        assessment = engine.assess_risk(proposed_notional_pct=20.0)
        assert VetoReason.EXPOSURE_CAP in assessment.vetos
        assert assessment.position_cap < 1.0

    def test_within_limits(self):
        config = RiskConfig(max_position_pct=10.0)
        engine = RiskEngine(config=config)
        assessment = engine.assess_risk(proposed_notional_pct=5.0)
        assert assessment.position_cap == 1.0


# === STATE ===
class TestStateManagement:
    def test_get_state(self):
        engine = RiskEngine()
        engine.update_equity(100.0)
        engine.update_equity(95.0)
        state = engine.get_state()
        assert state["peak_equity"] == 100.0
        assert state["current_equity"] == 95.0
        assert state["drawdown_pct"] == pytest.approx(5.0, abs=0.01)
        assert state["consecutive_losses"] == 0
        assert not state["is_circuit_open"]

    def test_reset_resets_peak(self):
        engine = RiskEngine()
        engine.update_equity(100.0)
        engine.update_equity(110.0)
        engine.update_equity(105.0)
        engine.reset()
        # After reset, peak = current = 105
        assert engine.current_drawdown_pct == 0.0

    def test_max_position_notional(self):
        config = RiskConfig(max_position_pct=10.0)
        engine = RiskEngine(config=config)
        assert engine.max_position_notional == 10.0

    def test_capped_in_bounds(self):
        engine = RiskEngine()
        assessment = engine.assess_risk()
        assert 0.0 <= assessment.position_cap <= 1.0


# === COMBO SCENARIOS ===
class TestComboScenarios:
    def test_multiple_soft_vetos(self):
        config = RiskConfig(max_position_pct=10.0, soft_drawdown_pct=3.0, max_drawdown_pct=10.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(96.0)  # 4% drawdown (soft reduction)
        for _ in range(10):
            engine.record_vol(40.0)  # High vol
        assessment = engine.assess_risk(signal_confidence=0.1, proposed_notional_pct=20.0)
        assert VetoReason.LOW_CONFIDENCE in assessment.vetos
        assert VetoReason.HIGH_VOLATILITY in assessment.vetos
        assert VetoReason.EXPOSURE_CAP in assessment.vetos

    def test_perfect_conditions(self):
        config = RiskConfig(max_position_pct=15.0)
        engine = RiskEngine(config=config)
        engine.update_equity(100.0)
        engine.update_equity(105.0)
        assessment = engine.assess_risk(signal_confidence=0.9, proposed_notional_pct=5.0)
        assert assessment.position_cap == 1.0
        assert not assessment.is_blocked
        assert len(assessment.vetos) == 0
        assert assessment.reason == ""
