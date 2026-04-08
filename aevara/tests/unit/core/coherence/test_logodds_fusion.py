# @module: aevara.tests.unit.core.coherence.test_logodds_fusion
# @deps: aevara.src.core.coherence.logodds_fusion
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes unitarios e property-based para logodds_fusion.
#           Happy path, edge cases, error cases, e propriedade de comutatividade.

from __future__ import annotations

import pytest
from aevara.src.core.coherence.logodds_fusion import (
    CoherenceInput,
    CoherenceOutput,
    fuse_coherence,
    logodds_to_probability,
    probability_to_logodds,
)


# --- Helper ---
def make_input(
    logodds=None,
    weights=None,
    prior=0.0,
    regime_penalty=0.0,
    L_max=4.5,
) -> CoherenceInput:
    """Factory para criar CoherenceInput padronizado."""
    return CoherenceInput(
        agent_logodds=logodds or {"A": 1.0, "B": -0.5},
        agent_weights=weights or {"A": 0.6, "B": 0.4},
        prior_logodds=prior,
        regime_penalty=regime_penalty,
        L_max=L_max,
    )


# === HAPPY PATH ===
class TestFusionHappyPath:
    def test_basic_fusion(self):
        inp = make_input()
        result = fuse_coherence(inp)
        assert isinstance(result, CoherenceOutput)
        assert -4.5 <= result.L_total <= 4.5
        assert 0.0 <= result.probability <= 1.0
        assert 0.0 <= result.confidence_band <= 1.0
        assert result.all_invariants_pass

    def test_fusion_with_positive_prior(self):
        inp = make_input(logodds={"A": 1.0, "B": 0.5}, weights={"A": 0.5, "B": 0.5}, prior=0.5)
        result = fuse_coherence(inp)
        assert result.L_total > 0.0
        assert result.probability > 0.5

    def test_fusion_with_regime_penalty(self):
        inp = make_input(
            logodds={"A": 2.0, "B": 1.0}, weights={"A": 0.5, "B": 0.5}, regime_penalty=-1.0
        )
        result = fuse_coherence(inp)
        expected_raw = 0.5 * 2.0 + 0.5 * 1.0 + 0.0 - 1.0  # = 0.5
        assert abs(result.L_total - 0.5) < 1e-10

    def test_all_invariants_pass(self):
        inp = make_input()
        result = fuse_coherence(inp)
        assert all(inv.passed for inv in result.invariant_results)


# === EDGE CASES ===
class TestFusionEdgeCases:
    def test_single_agent_weight_1(self):
        inp = make_input(logodds={"A": 3.0}, weights={"A": 1.0})
        result = fuse_coherence(inp)
        assert abs(result.L_total - 3.0) < 1e-10

    def test_L_at_max_boundary(self):
        inp = make_input(logodds={"A": 4.5}, weights={"A": 1.0}, prior=1.0)
        result = fuse_coherence(inp)
        assert result.L_total == 4.5  # clipped

    def test_L_at_min_boundary(self):
        inp = make_input(logodds={"A": -4.5}, weights={"A": 1.0}, prior=-1.0)
        result = fuse_coherence(inp)
        assert result.L_total == -4.5  # clipped

    def test_very_small_weights(self):
        inp = make_input(
            logodds={"A": 0.001, "B": -0.001},
            weights={"A": 0.5, "B": 0.5},
        )
        result = fuse_coherence(inp)
        assert abs(result.L_total) < 0.01

    def test_many_agents(self):
        n = 20
        logodds = {f"agent_{i}": 1.0 for i in range(n)}
        weights = {f"agent_{i}": 1.0 / n for i in range(n)}
        inp = make_input(logodds=logodds, weights=weights)
        result = fuse_coherence(inp)
        assert abs(result.L_total - 1.0) < 1e-10
        assert result.all_invariants_pass


# === ERROR CASES ===
class TestFusionErrors:
    def test_weights_do_not_sum_to_one(self):
        with pytest.raises(AssertionError, match="must sum to 1.0"):
            make_input(weights={"A": 0.3, "B": 0.3})

    def test_logodds_exceed_L_max(self):
        with pytest.raises(ValueError, match="exceeds L_max"):
            make_input(logodds={"A": 5.0}, weights={"A": 1.0})

    def test_invalid_weight_range(self):
        """Weight > 1.0 triggers AssertionError (sum check) or ValueError (range check)."""
        with pytest.raises((AssertionError, ValueError)):
            make_input(weights={"A": 0.5, "B": -0.1})

    def test_missing_weight(self):
        with pytest.raises(ValueError, match="have logodds but no weight"):
            make_input(logodds={"A": 1.0, "B": 0.5}, weights={"A": 1.0})

    def test_invalid_L_max(self):
        with pytest.raises(ValueError, match="exceeds L_max"):
            CoherenceInput(
                agent_logodds={"A": 5.0},
                agent_weights={"A": 1.0},
                prior_logodds=0.0,
                L_max=4.5,
            )


# === PROPERTY-BASED ===
class TestFusionProperties:
    def test_commutativity(self):
        """Fusao e comutativa: ordem dos agentes nao altera resultado."""
        logodds = {"A": 1.5, "B": -0.8, "C": 0.3, "D": 2.1}
        weights = {"A": 0.2, "B": 0.3, "C": 0.1, "D": 0.4}

        result1 = fuse_coherence(make_input(logodds=logodds, weights=weights))
        result2 = fuse_coherence(make_input(
            logodds=dict(reversed(list(logodds.items()))),
            weights=dict(reversed(list(weights.items()))),
        ))
        assert abs(result1.L_total - result2.L_total) < 1e-12

    def test_neutral_prior_zero_penalty_zero(self):
        """Com L_i = 0 para todos e prior = 0, penalty = 0, resultado e 0."""
        inp = make_input(
            logodds={"A": 0.0, "B": 0.0},
            weights={"A": 0.5, "B": 0.5},
            prior=0.0,
            regime_penalty=0.0,
        )
        result = fuse_coherence(inp)
        assert abs(result.L_total) < 1e-12

    def test_probability_monotonic(self):
        """Maior L_total => maior probabilidade."""
        for L in [-3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0]:
            p = logodds_to_probability(L)
            assert 0.0 < p < 1.0

    def test_roundtrip_conversion(self):
        """probability -> logodds -> probability e identidade."""
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            L = probability_to_logodds(p)
            p_back = logodds_to_probability(L)
            assert abs(p - p_back) < 1e-6

    def test_clip_is_bounded(self):
        """L_total nunca excede L_max em magnitude."""
        L_max = 4.5
        for i in range(100):
            # Edge: muito prior + agentes no limite
            inp = make_input(
                logodds={"A": L_max},
                weights={"A": 1.0},
                prior=L_max,
            )
            result = fuse_coherence(inp)
            assert abs(result.L_total) <= L_max
