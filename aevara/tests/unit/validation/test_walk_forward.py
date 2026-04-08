# @module: aevara.tests.unit.validation.test_walk_forward
# @deps: aevara.src.validation.walk_forward
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para WalkForwardEngine: rolling logic, regime stratification, OOS isolation, evaluation.

from __future__ import annotations

import numpy as np
import pytest

from aevara.src.validation.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
    WalkForwardResult,
)


def _make_returns(n=500):
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0001, 0.02, size=n)
    regimes = np.array(
        ["trending"] * 150 + ["ranging"] * 200 + ["crisis"] * (n - 350)
    )
    return returns, regimes


# === SPLIT GENERATION ===
class TestSplitGeneration:
    def test_generates_splits(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        assert len(splits) > 0

    def test_splits_have_required_fields(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        for s in splits:
            assert s.train_start >= 0
            assert s.train_end > s.train_start
            assert s.oos_start >= s.train_end
            assert s.oos_end > s.oos_start
            assert s.step >= 0

    def test_insufficient_data(self):
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(50, dtype=float), np.array(["a"] * 50))
        assert len(splits) == 0


# === LEAKAGE PREVENTION ===
class TestLeakagePrevention:
    def test_no_train_oos_overlap(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        assert engine.verify_no_leakage(splits)

    def test_oos_after_train(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        for s in splits:
            assert s.oos_start >= s.train_end


# === REGIME STRATIFICATION ===
class TestRegimeStratification:
    def test_stratified_by_regime(self):
        returns, regimes = _make_returns(600)
        engine = WalkForwardEngine(WalkForwardConfig(initial_train_size=100, oos_size=30, step_size=30))
        result = engine.generate_regime_stratified(np.arange(600, dtype=float), regimes)
        assert len(result) > 0
        for regime, splits in result.items():
            for s in splits:
                assert s.regime == regime

    def test_regimes_with_enough_data(self):
        ts = np.arange(1000, dtype=float)
        regimes = np.array(["bull"] * 500 + ["bear"] * 500)
        engine = WalkForwardEngine(WalkForwardConfig(initial_train_size=100, oos_size=50, step_size=50))
        result = engine.generate_regime_stratified(ts, regimes)
        assert len(result) >= 1


# === EVALUATION ===
class TestEvaluation:
    def test_evaluate_returns(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        result = engine.evaluate(returns, splits)
        assert isinstance(result, WalkForwardResult)
        assert result.total_steps == len(splits)
        assert result.max_drawdown >= 0.0
        assert 0.0 <= result.win_rate <= 1.0

    def test_evaluate_sharpe(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        result = engine.evaluate(returns, splits)
        assert isinstance(result.oos_sharpe, float)

    def test_empty_splits(self):
        returns, regimes = _make_returns(100)
        engine = WalkForwardEngine()
        result = engine.evaluate(returns, [])
        assert result.total_steps == 0
        assert result.oos_sharpe == 0.0

    def test_regime_results_populated(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        result = engine.evaluate(returns, splits)
        assert len(result.regime_results) >= 1
        for regime, metrics in result.regime_results.items():
            assert "mean" in metrics
            assert "std" in metrics
            assert "sharpe" in metrics
            assert "count" in metrics

    def test_n_per_regime_populated(self):
        returns, regimes = _make_returns(500)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        result = engine.evaluate(returns, splits)
        total = sum(result.n_per_regime.values())
        assert total > 0

    def test_positive_return_strategy(self):
        returns = np.ones(500) * 0.001  # Always positive return
        regimes = np.array(["bull"] * 500)
        engine = WalkForwardEngine(WalkForwardConfig(initial_train_size=200, oos_size=50, step_size=50))
        splits = engine.generate_splits(np.arange(500, dtype=float), regimes)
        result = engine.evaluate(returns, splits)
        assert result.mean_oos_return > 0
        assert result.win_rate == 1.0


# === EDGE CASES ===
class TestEdgeCases:
    def test_min_oos_samples_filter(self):
        engine = WalkForwardEngine(WalkForwardConfig(
            initial_train_size=200, oos_size=5, min_oos_samples=10
        ))
        splits = engine.generate_splits(np.arange(250, dtype=float), np.array(["a"] * 250))
        # oos_size=5 < min_oos_samples=10, so no splits
        assert len(splits) == 0

    def test_max_steps_limit(self):
        returns, regimes = _make_returns(1000)
        engine = WalkForwardEngine()
        splits = engine.generate_splits(np.arange(1000, dtype=float), regimes, max_steps=2)
        assert len(splits) <= 2

    def test_config_with_large_oos(self):
        engine = WalkForwardEngine(WalkForwardConfig(initial_train_size=100, oos_size=500))
        ts = np.arange(700, dtype=float)
        regimes = np.array(["a"] * 700)
        splits = engine.generate_splits(ts, regimes)
        if splits:
            s = splits[0]
            assert s.oos_end - s.oos_start <= 500
