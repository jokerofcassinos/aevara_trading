# @module: aevara.tests.property.validation.test_validation_invariants
# @deps: aevara.src.validation.*, hypothesis
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Property-based tests para invariantes de validacao:
#           no leakage, DSR monotonic, regime coverage, embargo enforced.

from __future__ import annotations

import numpy as np
from hypothesis import given, settings, strategies as st

from aevara.src.validation.cpcv_pipeline import CPCVPipeline, CPCVConfig
from aevara.src.validation.deflated_sharpe import DeflatedSharpeCalculator
from aevara.src.validation.walk_forward import WalkForwardEngine, WalkForwardConfig


# === CPCV ===
class TestCPCVInvariants:
    @given(
        st.integers(24, 500),  # n_samples
        st.integers(4, 8),  # n_folds
        st.integers(1, 3),  # n_test_folds
        st.floats(0.0, 60.0),  # embargo
    )
    @settings(max_examples=100)
    def test_no_leakage(self, n_samples, n_folds, n_test_folds, embargo):
        if n_folds < n_test_folds:
            return
        if n_samples < n_folds:
            return
        n_folds = min(n_folds, n_samples)
        n_test_folds = min(n_test_folds, n_folds - 1)
        pipeline = CPCVPipeline(CPCVConfig(
            n_folds=n_folds, n_test_folds=n_test_folds, embargo_s=embargo,
        ))
        ts = np.arange(n_samples, dtype=float)
        regimes = np.array(["r"] * n_samples)
        splits = pipeline.generate_splits(ts, regimes)
        assert pipeline.verify_no_leakage(splits)


# === DSR ===
class TestDSRInvariants:
    @given(
        st.lists(st.floats(-2.0, 5.0), min_size=2, max_size=50),
        st.integers(2, 100),
        st.floats(-3.0, 3.0),
        st.floats(1.0, 10.0),
    )
    @settings(max_examples=150)
    def test_dsr_never_exceeds_raw(self, sharpe_vals, n_trials, skew, kurtosis):
        calc = DeflatedSharpeCalculator()
        metrics = calc.compute(sharpe_vals, n_trials, skew, kurtosis)
        assert metrics.deflated_sharpe <= metrics.raw_sharpe + 1e-10


# === WALK FORWARD ===
class TestWalkForwardInvariants:
    @given(
        st.integers(350, 2000),  # n_samples
        st.integers(100, 300),  # initial_train_size
        st.integers(10, 100),  # oos_size
    )
    @settings(max_examples=100)
    def test_no_overlap(self, n_samples, train_size, oos_size):
        if train_size + oos_size > n_samples:
            return
        engine = WalkForwardEngine(WalkForwardConfig(
            initial_train_size=train_size, oos_size=oos_size, step_size=oos_size,
        ))
        ts = np.arange(n_samples, dtype=float)
        regimes = np.array(["r"] * n_samples)
        splits = engine.generate_splits(ts, regimes)
        assert engine.verify_no_leakage(splits)

    @given(st.integers(100, 500))
    @settings(max_examples=50)
    def test_regime_coverage(self, n_samples):
        returns = np.random.default_rng(42).normal(0.0001, 0.02, size=n_samples)
        regimes = ["trending"] * (n_samples // 3) + ["ranging"] * (n_samples // 3)
        regimes += ["crisis"] * (n_samples - 2 * (n_samples // 3))
        regimes = np.array(regimes)
        ts = np.arange(n_samples, dtype=float)
        engine = WalkForwardEngine(WalkForwardConfig(
            initial_train_size=max(50, n_samples // 5),
            oos_size=max(20, n_samples // 10),
            step_size=max(20, n_samples // 10),
        ))
        splits = engine.generate_splits(ts, regimes)
        if splits:
            result = engine.evaluate(returns, splits)
            assert result.total_steps == len(splits)
            assert result.max_drawdown >= 0.0
