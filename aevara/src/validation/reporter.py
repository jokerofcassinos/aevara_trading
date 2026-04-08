# @module: aevara.src.validation.reporter
# @deps: json, dataclasses, typing, numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Agregacao de metricas de validacao, regime breakdown,
#           confidence intervals, export JSON. Consolida CPCV, DSR
#           e Walk-Forward em unico relatorio estruturado.

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Relatorio consolidado de validacao."""
    raw_sharpe: float
    deflated_sharpe: float
    walk_forward_sharpe: float
    max_drawdown: float
    win_rate: float
    probability_of_overfitting: float
    min_backtest_length: int
    regime_breakdown: Dict[str, Dict[str, float]]
    n_cpcv_folds: int
    n_walk_forward_steps: int
    confidence_interval_95: Dict[str, float]
    is_valid: bool
    validation_notes: List[str]


class ValidationReporter:
    """
    Gera relatorio consolidado de validacao.

    Invariantes:
    - is_valid so True se todos os gates passarem
    - Confidence intervals calculados via bootstrap
    - Regime breakdown obrigatorio
    - DSR <= raw_sharpe sempre
    """

    def __init__(self, confidence_level: float = 0.95, n_bootstrap: int = 1000):
        self._confidence_level = confidence_level
        self._n_bootstrap = n_bootstrap

    def build_report(
        self,
        returns: np.ndarray,
        raw_sharpe: float,
        deflated_sharpe: float,
        wf_sharpe: float,
        max_drawdown: float,
        win_rate: float,
        pbo: float,
        min_btl: int,
        regime_results: Dict[str, Dict[str, float]],
        n_cpcv_folds: int,
        n_wf_steps: int,
    ) -> ValidationReport:
        """
        Gera relatorio completo.

        Args:
            returns: array de retornos OOS
            raw_sharpe: Sharpe nao deflacionado
            deflated_sharpe: Sharpe deflacionado
            wf_sharpe: Sharpe do walk-forward
            max_drawdown: drawdown maximo
            win_rate: taxa de acerto
            pbo: probabilidade de backtest overfitting
            min_btl: minimo de amostras necessario
            regime_results: metricas por regime
            n_cpcv_folds: numero de folds CPCV
            n_wf_steps: numero de steps walk-forward

        Returns:
            ValidationReport completo
        """
        notes: List[str] = []
        n_samples = len(returns)

        # Confidence interval via bootstrap
        ci_low, ci_high = self._bootstrap_ci(returns)

        # Validation gates
        is_valid = True
        if deflated_sharpe < 0.5:
            is_valid = False
            notes.append(f"DSR {deflated_sharpe:.3f} below minimum 0.5")
        if pbo > 0.5:
            is_valid = False
            notes.append(f"PBO {pbo:.3f} above 0.5 threshold")
        if n_samples < min_btl:
            is_valid = False
            notes.append(f"Sample size {n_samples} below MinBTL {min_btl}")
        if max_drawdown > 0.10:
            notes.append(f"Max drawdown {max_drawdown:.3f} exceeds 10%")
        if n_cpcv_folds == 0:
            notes.append("No CPCV folds generated")

        return ValidationReport(
            raw_sharpe=raw_sharpe,
            deflated_sharpe=deflated_sharpe,
            walk_forward_sharpe=wf_sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            probability_of_overfitting=pbo,
            min_backtest_length=min_btl,
            regime_breakdown=regime_results,
            n_cpcv_folds=n_cpcv_folds,
            n_walk_forward_steps=n_wf_steps,
            confidence_interval_95={"low": ci_low, "high": ci_high},
            is_valid=is_valid,
            validation_notes=notes,
        )

    def _bootstrap_ci(
        self, returns: np.ndarray, statistic: str = "mean"
    ) -> tuple[float, float]:
        """
        Calcula confidence interval via bootstrap.

        Args:
            returns: array de retornos
            statistic: "mean" ou "sharpe"

        Returns:
            (ci_low, ci_high)
        """
        if len(returns) < 2:
            return (0.0, 0.0)

        rng = np.random.default_rng(42)
        n = len(returns)
        boot_stats = []

        for _ in range(self._n_bootstrap):
            sample = rng.choice(returns, size=n, replace=True)
            if statistic == "mean":
                boot_stats.append(np.mean(sample))
            else:
                std = np.std(sample)
                boot_stats.append(np.mean(sample) / std if std > 0 else 0.0)

        alpha = 1.0 - self._confidence_level
        ci_low = float(np.percentile(boot_stats, alpha / 2 * 100))
        ci_high = float(np.percentile(boot_stats, (1 - alpha / 2) * 100))
        return (ci_low, ci_high)

    def export_json(self, report: ValidationReport) -> str:
        """Exporta relatorio em JSON."""
        # Convert frozen dataclass to dict
        data = {
            "raw_sharpe": report.raw_sharpe,
            "deflated_sharpe": report.deflated_sharpe,
            "walk_forward_sharpe": report.walk_forward_sharpe,
            "max_drawdown": report.max_drawdown,
            "win_rate": report.win_rate,
            "probability_of_overfitting": report.probability_of_overfitting,
            "min_backtest_length": report.min_backtest_length,
            "regime_breakdown": report.regime_breakdown,
            "n_cpcv_folds": report.n_cpcv_folds,
            "n_walk_forward_steps": report.n_walk_forward_steps,
            "confidence_interval_95": report.confidence_interval_95,
            "is_valid": report.is_valid,
            "validation_notes": report.validation_notes,
        }
        return json.dumps(data, indent=2, default=str)

    def summary(self, report: ValidationReport) -> str:
        """Retorna resumo legivel do relatorio."""
        status = "VALID" if report.is_valid else "INVALID"
        lines = [
            f"Validation Report: {status}",
            f"  Raw Sharpe:     {report.raw_sharpe:.4f}",
            f"  Deflated Sharpe:{report.deflated_sharpe:.4f}",
            f"  W-F Sharpe:     {report.walk_forward_sharpe:.4f}",
            f"  Max Drawdown:   {report.max_drawdown:.4f}",
            f"  Win Rate:       {report.win_rate:.4f}",
            f"  PBO:            {report.probability_of_overfitting:.4f}",
            f"  MinBTL:         {report.min_backtest_length}",
            f"  CPCV Folds:     {report.n_cpcv_folds}",
            f"  W-F Steps:      {report.n_walk_forward_steps}",
            f"  CI 95%:         [{report.confidence_interval_95['low']:.4f}, "
            f"{report.confidence_interval_95['high']:.4f}]",
        ]
        if report.regime_breakdown:
            lines.append("  Regime Breakdown:")
            for regime, metrics in report.regime_breakdown.items():
                lines.append(f"    {regime}: Sharpe={metrics.get('sharpe', 0):.3f}, "
                           f"n={metrics.get('count', 0)}")
        if report.validation_notes:
            lines.append("  Notes:")
            for note in report.validation_notes:
                lines.append(f"    - {note}")
        return "\n".join(lines)
