# @module: aevara.tests.unit.validation.test_deflated_sharpe
# @deps: aevara.src.validation.deflated_sharpe
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para Deflated Sharpe: DSR deflation, MinBTL, PBO bounds.

from __future__ import annotations

import numpy as np
import pytest

from aevara.src.validation.deflated_sharpe import (
    DeflatedSharpeCalculator,
    DeflatedSharpeConfig,
    SharpeMetrics,
)


# === DSR DEFLECTION ===
class TestDeflatedSharpe:
    def test_dsr_less_than_raw(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([0.5, 0.8, 1.2, 1.5, 1.0], n_trials=10)
        assert metrics.deflated_sharpe <= metrics.raw_sharpe

    def test_dsr_positive(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([1.0, 1.5, 2.0], n_trials=5)
        assert metrics.deflated_sharpe >= 0.0

    def test_dsr_increases_with_raw(self):
        calc = DeflatedSharpeCalculator()
        m1 = calc.compute([0.5, 0.6, 0.7], n_trials=5)
        m2 = calc.compute([1.0, 1.2, 1.5], n_trials=5)
        assert m2.deflated_sharpe >= m1.deflated_sharpe

    def test_dsr_decreases_with_more_trials(self):
        calc = DeflatedSharpeCalculator()
        sharpe_vals = [1.0, 1.2, 1.5]
        m1 = calc.compute(sharpe_vals, n_trials=5)
        m2 = calc.compute(sharpe_vals, n_trials=100)
        assert m2.deflated_sharpe <= m1.deflated_sharpe

    def test_empty_input(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([], n_trials=5)
        assert metrics.raw_sharpe == 0.0
        assert metrics.deflated_sharpe == 0.0
        assert metrics.probability_of_overfitting == 1.0

    def test_single_trial_no_deflation(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([1.5], n_trials=1)
        assert metrics.deflated_sharpe >= 0

    def test_with_skew_and_kurtosis(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([1.0, 1.2, 1.5], n_trials=10,
                              skew=-0.5, kurtosis=5.0)
        assert metrics.deflated_sharpe <= metrics.raw_sharpe
        assert metrics.deflated_sharpe >= 0.0


# === MINBTL ===
class TestMinBTL:
    def test_min_btl_positive(self):
        calc = DeflatedSharpeCalculator()
        btl = calc.min_backtest_length(1.0)
        assert btl >= 1

    def test_min_btl_decreases_with_higher_sharpe(self):
        calc = DeflatedSharpeCalculator()
        btl_low = calc.min_backtest_length(0.5)
        btl_high = calc.min_backtest_length(2.0)
        assert btl_high < btl_low

    def test_min_btl_zero_sharpe_returns_one(self):
        calc = DeflatedSharpeCalculator()
        btl = calc.min_backtest_length(0.0)
        assert btl == 1

    def test_min_btl_increases_with_variance(self):
        calc = DeflatedSharpeCalculator()
        btl1 = calc.min_backtest_length(1.0, target_sr_variance=1.0)
        btl2 = calc.min_backtest_length(1.0, target_sr_variance=4.0)
        assert btl2 >= btl1


# === PBO ===
class TestPBO:
    def test_pbo_in_bounds(self):
        calc = DeflatedSharpeCalculator()
        pbo = calc.probability_of_backtest_overfitting(
            np.array([1, 0, 1, 1, 0])
        )
        assert 0.0 <= pbo <= 1.0

    def test_pbo_all_overfit(self):
        calc = DeflatedSharpeCalculator()
        pbo = calc.probability_of_backtest_overfitting(
            np.array([1, 1, 1, 1, 1])
        )
        assert pbo == 1.0

    def test_pbo_no_overfit(self):
        calc = DeflatedSharpeCalculator()
        pbo = calc.probability_of_backtest_overfitting(
            np.array([0, 0, 0, 0, 0])
        )
        assert pbo == 0.0

    def test_pbo_empty_input(self):
        calc = DeflatedSharpeCalculator()
        import numpy as np
        pbo = calc.probability_of_backtest_overfitting(np.array([]))
        assert pbo == 1.0

    def test_pbo_from_spread(self):
        calc = DeflatedSharpeCalculator()
        pbo_low = calc._pbo_from_sharpe_spread(0.5, 10, 3.0)
        pbo_high = calc._pbo_from_sharpe_spread(3.0, 10, 3.0)
        assert pbo_high >= pbo_low

    def test_correlation_computation(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute([1.0, 1.1, 0.9, 1.05], n_trials=5)
        assert 0.0 <= metrics.correlation_of_trials <= 1.0


# === INTEGRATION ===
class TestSharpeIntegration:
    def test_full_pipeline(self):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute(
            sharpe_values=[0.8, 1.2, 0.5, 1.5, 0.9],
            n_trials=20,
            skew=-0.3,
            kurtosis=4.0,
        )
        assert isinstance(metrics, SharpeMetrics)
        assert metrics.raw_sharpe == 1.5
        assert metrics.deflated_sharpe <= 1.5
        assert metrics.deflated_sharpe >= 0.0
        assert metrics.min_backtest_length >= 1
        assert 0.0 <= metrics.probability_of_overfitting <= 1.0
        assert 0.0 <= metrics.correlation_of_trials <= 1.0

    def test_config_override(self):
        config = DeflatedSharpeConfig(target_sharpe=2.0)
        calc = DeflatedSharpeCalculator(config=config)
        btl = calc.min_backtest_length(1.5)
        assert btl >= 1
