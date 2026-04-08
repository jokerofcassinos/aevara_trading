# @module: aevara.tests.unit.risk.test_position_sizing
# @deps: aevara.src.risk.position_sizing
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para PositionSizer: Kelly criterion, fractional Kelly, volatility targeting, CVaR floor, dust trades.

from __future__ import annotations

import pytest

from aevara.src.risk.position_sizing import (
    PositionSize,
    PositionSizer,
    SizingConfig,
)


# === KELLY CRITERION ===
class TestKellyCriterion:
    def test_kelly_formula(self):
        # K = p - q/b, where b = avg_win/avg_loss
        # p=0.55, avg_win=2%, avg_loss=1% -> b=2, q=0.45
        # K = 0.55 - 0.45/2 = 0.55 - 0.225 = 0.325
        kelly = PositionSizer.kelly_criterion(0.55, 2.0, 1.0)
        assert kelly == pytest.approx(0.325, abs=0.001)

    def test_kelly_edge_case_50_50(self):
        # p=0.5, b=1 -> K = 0.5 - 0.5/1 = 0
        kelly = PositionSizer.kelly_criterion(0.5, 1.0, 1.0)
        assert kelly == pytest.approx(0.0, abs=0.001)

    def test_kelly_no_edge_returns_zero(self):
        # Edge is negative: p=0.4, b=1 -> K = 0.4 - 0.6 = -0.2 -> 0
        kelly = PositionSizer.kelly_criterion(0.4, 1.0, 1.0)
        assert kelly == pytest.approx(0.0, abs=0.001)

    def test_kelly_strong_edge(self):
        # p=0.6, b=2 -> K = 0.6 - 0.4/2 = 0.6 - 0.2 = 0.4
        kelly = PositionSizer.kelly_criterion(0.6, 2.0, 1.0)
        assert kelly == pytest.approx(0.4, abs=0.001)

    def test_kelly_zero_win_rate(self):
        kelly = PositionSizer.kelly_criterion(0.0, 2.0, 1.0)
        assert kelly == 0.0

    def test_kelly_perfect_win_rate_ignored(self):
        # win_rate=1.0 returns 0 (edge case guard)
        kelly = PositionSizer.kelly_criterion(1.0, 2.0, 1.0)
        assert kelly == 0.0

    def test_kelly_zero_loss_returns_zero(self):
        kelly = PositionSizer.kelly_criterion(0.6, 2.0, 0.0)
        assert kelly == 0.0

    def test_kelly_zero_win_returns_zero(self):
        kelly = PositionSizer.kelly_criterion(0.6, 0.0, 1.0)
        assert kelly == 0.0


# === POSITION SIZING ===
class TestPositionCalculation:
    def test_fractional_kelly(self):
        config = SizingConfig(kelly_fraction=0.25, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        # Kelly raw = 0.325 -> fractional = 0.08125 -> 8.125%
        result = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        assert result.kelly_raw == pytest.approx(0.325, abs=0.001)
        assert result.kelly_adjusted == pytest.approx(0.325 * 0.25, abs=0.01)
        assert result.notional_pct > 0

    def test_vol_adjustment_reduces_size_when_high_vol(self):
        config = SizingConfig(kelly_fraction=1.0, vol_target_pct=15.0,
                              cvar_floor_pct=100.0, max_position_pct=50.0)
        sizer = PositionSizer(config=config)
        vol_low = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        vol_high = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=30.0, risk_cap=1.0
        )
        assert vol_high.kelly_adjusted < vol_low.kelly_adjusted

    def test_vol_zero_no_adjustment(self):
        config = SizingConfig(kelly_fraction=1.0, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=0.0, risk_cap=1.0
        )
        assert result.kelly_adjusted == pytest.approx(0.325, abs=0.001)

    def test_leverage_cap(self):
        config = SizingConfig(kelly_fraction=1.0, max_leverage=0.1, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.7, avg_win_pct=5.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        # Kelly raw for p=0.7, b=5: K = 0.7 - 0.3/5 = 0.7 - 0.06 = 0.64
        # Capped at max_leverage=0.1
        assert result.kelly_adjusted == pytest.approx(0.1, abs=0.01)

    def test_risk_cap_reduction(self):
        config = SizingConfig(kelly_fraction=1.0, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        full = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        half_cap = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=0.5
        )
        assert half_cap.notional_pct == pytest.approx(full.notional_pct * 0.5, abs=0.01)

    def test_dust_trade_returns_zero(self):
        config = SizingConfig(kelly_fraction=0.25, vol_target_pct=15.0, min_position_pct=1.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.51, avg_win_pct=0.1, avg_loss_pct=0.1,
            current_vol_pct=15.0, risk_cap=1.0
        )
        # Very weak edge -> tiny Kelly -> below min_position
        assert result.is_dust
        assert result.notional_pct == 0.0

    def test_no_edge_returns_zero(self):
        config = SizingConfig(kelly_fraction=0.25, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.5, avg_win_pct=1.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        assert result.kelly_raw == 0.0
        assert result.notional_pct == 0.0

    def test_cvar_floor_limits_position(self):
        config = SizingConfig(
            kelly_fraction=1.0, vol_target_pct=15.0,
            cvar_floor_pct=1.0, return_per_trade_pct=1.0
        )
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.7, avg_win_pct=10.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        # Kelly would be huge, but CVaR caps it:
        # worst_case = notional * 1.0 * 3 > 1.0 -> notional < 1/3
        assert result.notional_pct < 1.0 / (1.0 * 3.0) + 0.02


# === POSITION SIZE STRUCT ===
class TestPositionSizeStruct:
    def test_fields_populated(self):
        config = SizingConfig(kelly_fraction=0.5, vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.55, avg_win_pct=2.0, avg_loss_pct=1.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        assert result.kelly_raw >= 0
        assert result.kelly_adjusted >= 0
        assert result.risk_cap_applied == 1.0
        assert result.final_notional == result.notional_pct
        assert 0.0 <= result.notional_pct <= config.max_position_pct


# === CONFIG ===
class TestSizingConfig:
    def test_default_config(self):
        sizer = PositionSizer()
        config = sizer.get_config()
        assert config["kelly_fraction"] == 0.25
        assert config["max_leverage"] == 1.0
        assert config["cvar_floor_pct"] == 2.0

    def test_custom_config(self):
        config = SizingConfig(kelly_fraction=0.5, max_leverage=2.0)
        sizer = PositionSizer(config=config)
        c = sizer.get_config()
        assert c["kelly_fraction"] == 0.5
        assert c["max_leverage"] == 2.0


# === BOUNDS ===
class TestPositionBounds:
    def test_never_exceeds_max_position(self):
        config = SizingConfig(kelly_fraction=1.0, vol_target_pct=15.0, max_position_pct=5.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.8, avg_win_pct=10.0, avg_loss_pct=0.5,
            current_vol_pct=5.0, risk_cap=1.0
        )
        assert result.notional_pct <= 5.0

    def test_never_negative(self):
        config = SizingConfig(vol_target_pct=15.0)
        sizer = PositionSizer(config=config)
        result = sizer.calculate_position(
            win_rate=0.3, avg_win_pct=1.0, avg_loss_pct=2.0,
            current_vol_pct=15.0, risk_cap=1.0
        )
        assert result.notional_pct >= 0.0
