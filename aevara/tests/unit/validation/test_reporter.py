# @module: aevara.tests.unit.validation.test_reporter
# @deps: aevara.src.validation.reporter
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para ValidationReporter: report generation, CI, JSON export, summary.

from __future__ import annotations

import json

import numpy as np
import pytest

from aevara.src.validation.reporter import ValidationReporter, ValidationReport


def _make_report(overrides: dict = {}):
    reporter = ValidationReporter()
    defaults = {
        "returns": np.random.default_rng(42).normal(0.001, 0.02, 500),
        "raw_sharpe": 1.5,
        "deflated_sharpe": 1.0,
        "wf_sharpe": 0.9,
        "max_drawdown": 0.05,
        "win_rate": 0.55,
        "pbo": 0.15,
        "min_btl": 200,
        "regime_results": {"trending": {"sharpe": 1.2, "count": 200}},
        "n_cpcv_folds": 15,
        "n_wf_steps": 10,
    }
    defaults.update(overrides)
    return reporter.build_report(**defaults), reporter


# === REPORT GENERATION ===
class TestReportGeneration:
    def test_build_valid_report(self):
        report, _ = _make_report()
        assert report.is_valid
        assert len(report.validation_notes) == 0

    def test_invalid_when_dsr_low(self):
        report, _ = _make_report({"deflated_sharpe": 0.3})
        assert not report.is_valid
        assert any("DSR" in n for n in report.validation_notes)

    def test_invalid_when_pbo_high(self):
        report, _ = _make_report({"pbo": 0.6})
        assert not report.is_valid
        assert any("PBO" in n for n in report.validation_notes)

    def test_invalid_when_under_min_btl(self):
        report, _ = _make_report({
            "returns": np.array([0.01] * 50),
            "min_btl": 200,
        })
        assert not report.is_valid
        assert any("MinBTL" in n for n in report.validation_notes)

    def test_drawdown_note(self):
        report, _ = _make_report({"max_drawdown": 0.15})
        assert any("drawdown" in n.lower() for n in report.validation_notes)

    def test_ci_bounded(self):
        report, _ = _make_report()
        ci = report.confidence_interval_95
        assert ci["low"] <= ci["high"]

    def test_regime_breakdown_populated(self):
        report, _ = _make_report()
        assert "trending" in report.regime_breakdown
        assert "sharpe" in report.regime_breakdown["trending"]


# === JSON EXPORT ===
class TestJsonExport:
    def test_exports_valid_json(self):
        report, reporter = _make_report()
        json_str = reporter.export_json(report)
        data = json.loads(json_str)
        assert data["raw_sharpe"] == 1.5
        assert data["is_valid"] is True

    def test_contains_all_fields(self):
        report, reporter = _make_report()
        json_str = reporter.export_json(report)
        data = json.loads(json_str)
        required_fields = [
            "raw_sharpe", "deflated_sharpe", "walk_forward_sharpe",
            "max_drawdown", "win_rate", "probability_of_overfitting",
            "min_backtest_length", "regime_breakdown", "n_cpcv_folds",
            "n_walk_forward_steps", "confidence_interval_95",
            "is_valid", "validation_notes",
        ]
        for f in required_fields:
            assert f in data


# === SUMMARY ===
class TestSummary:
    def test_summary_contains_key_metrics(self):
        report, reporter = _make_report()
        summary = reporter.summary(report)
        assert "Valid" in summary
        assert "1.5" in summary  # raw_sharpe
        assert "1.0" in summary  # deflated_sharpe

    def test_summary_shows_notes_when_invalid(self):
        report, reporter = _make_report({"deflated_sharpe": 0.3})
        summary = reporter.summary(report)
        assert "INVALID" in summary
        assert "DSR" in summary

    def test_summary_shows_regime_breakdown(self):
        report, reporter = _make_report()
        summary = reporter.summary(report)
        assert "Regime Breakdown" in summary
        assert "trending" in summary
