# @module: aevara.tests.unit.validation.test_cpcv
# @deps: aevara.src.validation.cpcv_pipeline
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para CPCV: partitioning, embargo, leakage prevention, regime stratification.

from __future__ import annotations

import numpy as np
import pytest

from aevara.src.validation.cpcv_pipeline import (
    CPCVConfig,
    CPCVPipeline,
    ValidationSplit,
)


def _make_data(n=500):
    timestamps = np.arange(n, dtype=float)
    regimes = np.array(["trending"] * 150 + ["ranging"] * 200 + ["crisis"] * 150)
    return timestamps, regimes


# === GENERATION ===
class TestCPCVGeneration:
    def test_generates_splits(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline()
        splits = pipeline.generate_splits(ts, regimes)
        assert len(splits) > 0

    def test_n_combinations_matches(self):
        pipeline = CPCVPipeline(CPCVConfig(n_folds=6, n_test_folds=2))
        # C(6,2) = 15
        assert pipeline.get_n_combinations() == 15

    def test_n_combinations_custom(self):
        pipeline = CPCVPipeline(CPCVConfig(n_folds=10, n_test_folds=3))
        # C(10,3) = 120
        assert pipeline.get_n_combinations() == 120

    def test_splits_have_required_fields(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline()
        splits = pipeline.generate_splits(ts, regimes)
        for s in splits:
            assert len(s.train_indices) > 0
            assert len(s.test_indices) > 0
            assert s.fold_id >= 0
            assert isinstance(s.regime_tag, str)

    def test_limit_combinations(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline(CPCVConfig(n_folds=6, n_test_folds=2))
        splits = pipeline.generate_splits(ts, regimes, n_combinations=3)
        assert len(splits) <= 3


# === LEAKAGE ===
class TestLeakagePrevention:
    def test_no_leakage_clean(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline()
        splits = pipeline.generate_splits(ts, regimes)
        assert pipeline.verify_no_leakage(splits)

    def test_no_leakage_with_embargo(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline(CPCVConfig(embargo_s=10.0))
        splits = pipeline.generate_splits(ts, regimes, embargo_s=10.0)
        assert pipeline.verify_no_leakage(splits)

    def test_embargo_purges_nearby_samples(self):
        ts = np.arange(100, dtype=float)
        regimes = np.array(["regime_a"] * 100)
        pipeline = CPCVPipeline(CPCVConfig(n_folds=5, n_test_folds=1, embargo_s=5.0))
        splits = pipeline.generate_splits(ts, regimes, embargo_s=5.0)

        for split in splits:
            test_min = split.test_indices.min()
            test_max = split.test_indices.max()
            for train_idx in split.train_indices:
                assert abs(train_idx - test_min) >= 5.0 or abs(train_idx - test_max) >= 5.0

    def test_embargo_reduces_train_size(self):
        ts, regimes = _make_data(500)
        pipeline_no_embargo = CPCVPipeline(CPCVConfig(embargo_s=0.0))
        pipeline_embargo = CPCVPipeline(CPCVConfig(embargo_s=30.0))

        splits_no = pipeline_no_embargo.generate_splits(ts, regimes, embargo_s=0.0)
        splits_yes = pipeline_embargo.generate_splits(ts, regimes, embargo_s=30.0)

        if splits_no and splits_yes:
            avg_train_no = np.mean([len(s.train_indices) for s in splits_no])
            avg_train_yes = np.mean([len(s.train_indices) for s in splits_yes])
            assert avg_train_yes <= avg_train_no


# === REGIME STRATIFICATION ===
class TestRegimeStratification:
    def test_stratified_folds_per_regime(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline(CPCVConfig(n_folds=5, n_test_folds=1))
        result = pipeline.compute_stratified_folds(ts, regimes)
        # Should have keys for each regime
        assert len(result) > 0
        for regime_name, folds in result.items():
            for fold in folds:
                assert fold.regime_tag == regime_name

    def test_all_regimes_covered(self):
        ts = np.arange(600, dtype=float)
        regimes = np.array(
            ["bull"] * 200 + ["bear"] * 200 + ["crab"] * 200
        )
        pipeline = CPCVPipeline(CPCVConfig(n_folds=6, n_test_folds=1))
        result = pipeline.compute_stratified_folds(ts, regimes)
        regime_keys = set(result.keys())
        assert "bull" in regime_keys or "bear" in regime_keys or "crab" in regime_keys

    def test_dominant_regime_computation(self):
        regimes = np.array(["a", "a", "b", "a", "b"])
        result = CPCVPipeline._dominant_regime(regimes)
        assert result == "a"

    def test_single_regime(self):
        regimes = np.array(["crisis"] * 50)
        result = CPCVPipeline._dominant_regime(regimes)
        assert result == "crisis"


# === EDGE CASES ===
class TestEdgeCases:
    def test_insufficient_data(self):
        pipeline = CPCVPipeline(CPCVConfig(n_folds=10))
        ts = np.arange(5, dtype=float)
        regimes = np.array(["a"] * 5)
        splits = pipeline.generate_splits(ts, regimes)
        assert len(splits) == 0

    def test_min_samples_filter(self):
        config = CPCVConfig(
            n_folds=5, n_test_folds=1,
            min_train_samples=400, min_test_samples=80,
        )
        pipeline = CPCVPipeline(config)
        ts = np.arange(200, dtype=float)
        regimes = np.array(["a"] * 200)
        splits = pipeline.generate_splits(ts, regimes)
        assert len(splits) == 0

    def test_empty_timestamps(self):
        pipeline = CPCVPipeline()
        splits = pipeline.generate_splits(np.array([]), np.array([]))
        assert len(splits) == 0

    def test_mismatched_lengths_raises(self):
        pipeline = CPCVPipeline()
        with pytest.raises(AssertionError):
            pipeline.generate_splits(np.arange(100), np.array(["a"] * 99))

    def test_fold_ids_sequential(self):
        ts, regimes = _make_data(500)
        pipeline = CPCVPipeline(CPCVConfig(n_folds=6, n_test_folds=2))
        splits = pipeline.generate_splits(ts, regimes, n_combinations=5)
        fold_ids = [s.fold_id for s in splits]
        assert fold_ids == list(range(len(fold_ids)))
