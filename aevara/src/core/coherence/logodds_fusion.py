# @module: aevara.src.core.coherence.logodds_fusion
# @deps: aevara.src.utils.math, aevara.src.core.invariants
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Fusão de log-odds de multiplos agentes com pesos mutaveis via DNA.
#           L_total = Sigma(w_i * L_i) + L_prior + L_regime_penalty.
#           Output: float em espaco log-odds, clipado em [-L_max, L_max].
#           Este e o nucleo cognitivo do Aevra: agrega sinais heterogeneos em
#           uma unica medida coerente de confianca direcional.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aevara.src.utils.math import clip, logit, sigmoid, safe_log
from aevara.src.core.invariants import (
    InvariantResult,
    aggregate_invariants,
    format_invariant_report,
    validate_coherence_invariants,
)


@dataclass(frozen=True, slots=True)
class CoherenceInput:
    """
    Contrato de entrada para fusão de coerência.
    Todos os campos são imutaveis por construção (frozen=True, slots=True).
    Invariantes validados em __post_init__.
    """
    agent_logodds: Dict[str, float]   # {agent_id: L_i}
    agent_weights: Dict[str, float]   # {agent_id: w_i}, deve somar 1.0
    prior_logodds: float              # L_prior (viés estrutural)
    regime_penalty: float = 0.0       # Penalidade se sinal contradiz regime
    L_max: float = 4.5                # Clip numérico para estabilidade

    def __post_init__(self) -> None:
        """Validação de invariantes na construção."""
        # INV: Weights must sum to 1.0
        weight_sum = sum(self.agent_weights.values())
        assert abs(weight_sum - 1.0) < 1e-6, (
            f"Agent weights must sum to 1.0, got {weight_sum:.10f}"
        )

        # INV: All L_i within [-L_max, L_max]
        for agent_id, L_i in self.agent_logodds.items():
            if abs(L_i) > self.L_max:
                raise ValueError(
                    f"L_i for '{agent_id}' = {L_i} exceeds L_max={self.L_max}"
                )

        # INV: All weights in [0, 1]
        for agent_id, w in self.agent_weights.items():
            if not (0.0 <= w <= 1.0):
                raise ValueError(
                    f"Weight for '{agent_id}' = {w} not in [0, 1]"
                )

        # INV: Consistency - every agent with L_i must have a weight
        logodds_keys = set(self.agent_logodds.keys())
        weight_keys = set(self.agent_weights.keys())
        if not weight_keys.issuperset(logodds_keys):
            missing = logodds_keys - weight_keys
            raise ValueError(f"Agents {missing} have logodds but no weight")


@dataclass(frozen=True, slots=True)
class CoherenceOutput:
    """Contrato de saída da fusão de coerência."""
    L_total: float                     # Log-odds total clipado
    L_weighted_sum: float             # Componente Sigma(w_i * L_i)
    L_prior: float                    # Componente prior
    L_regime_penalty: float           # Componente penalidade
    probability: float                # p = sigmoid(L_total)
    confidence_band: float            # |L_total| / L_max (normalizado [0,1])
    invariant_results: Tuple[InvariantResult, ...]
    all_invariants_pass: bool


def fuse_coherence(input: CoherenceInput) -> CoherenceOutput:
    """
    Fusão de log-odds: L_total = Sigma(w_i * L_i) + L_prior + L_regime_penalty

    Decomposicao matematica:
    - Agregação ponderada:Sigma(w_i * L_i) onde Sigma w_i = 1.0
    - Prior estrutural: viés de longo prazo (tipicamente ~0 para mercado eficiente)
    - Penalidade de regime: ajuste quando o sinal contradiz o regime detectado
      (ex: sinal bullish em regime bearish -> penalty > 0 reduzindo L_total)
    - Clip final: L_total em [-L_max, L_max] para estabilidade numerica

    Complexidade: O(n) onde n = numero de agentes (tipicamente 3-8)

    Args:
        input: CoherenceInput com contratos validados

    Returns:
        CoherenceOutput com L_total, probabilidade, e resultados de invariantes
    """
    # Stage 1: Agregação ponderada
    L_weighted_sum = sum(
        input.agent_weights[agent_id] * L_i
        for agent_id, L_i in input.agent_logodds.items()
    )

    # Stage 2: Composição com prior e penalidade
    L_raw = L_weighted_sum + input.prior_logodds + input.regime_penalty

    # Stage 3: Clip numérico para estabilidade
    L_total = clip(L_raw, -input.L_max, input.L_max)

    # Stage 4: Derivações
    probability = sigmoid(L_total)
    confidence_band = abs(L_total) / input.L_max if input.L_max > 0 else 0.0

    # Stage 5: Validação de invariantes
    inv_results = validate_coherence_invariants(L_total, input)
    all_pass = aggregate_invariants(inv_results)

    return CoherenceOutput(
        L_total=L_total,
        L_weighted_sum=L_weighted_sum,
        L_prior=input.prior_logodds,
        L_regime_penalty=input.regime_penalty,
        probability=probability,
        confidence_band=confidence_band,
        invariant_results=tuple(inv_results),
        all_invariants_pass=all_pass,
    )


def logodds_to_probability(L: float, epsilon: float = 1e-8) -> float:
    """Converte log-odds para probabilidade: p = 1 / (1 + exp(-L))"""
    return sigmoid(L, epsilon)


def probability_to_logodds(p: float, epsilon: float = 1e-8) -> float:
    """Converte probabilidade para log-odds: L = log(p / (1-p))"""
    p = clip(p, epsilon, 1.0 - epsilon)  # Evitar log(0)
    return logit(p, epsilon)


def merge_coherence_inputs(
    inputs: List[CoherenceInput],
    merge_weights: Optional[List[float]] = None,
) -> CoherenceInput:
    """
    Merge múltiplos CoherenceInputs em um único input (para fusão hierarquica).

    Args:
        inputs: Lista de CoherenceInput para merge
        merge_weights: Pesos para cada input (default: equal weight)

    Returns:
        CoherenceInput merged com todos os agentes e pesos re-normalizados
    """
    if len(inputs) == 1:
        return inputs[0]

    n = len(inputs)
    if merge_weights is None:
        merge_weights = [1.0 / n] * n

    assert len(merge_weights) == n, "merge_weights length must match inputs length"

    # Merge all agents
    merged_logodds: Dict[str, float] = {}
    merged_weights: Dict[str, float] = {}
    L_max = max(inp.L_max for inp in inputs)

    # Weighted merge of agent logodds
    for inp, mw in zip(inputs, merge_weights):
        for agent_id, L_i in inp.agent_logodds.items():
            if agent_id in merged_logodds:
                # Average if agent appears in multiple inputs
                merged_logodds[agent_id] = (merged_logodds[agent_id] + L_i * mw) / 2.0
            else:
                merged_logodds[agent_id] = L_i * mw

    # Sum weights per agent, then normalize
    for inp, mw in zip(inputs, merge_weights):
        for agent_id, w in inp.agent_weights.items():
            merged_weights[agent_id] = merged_weights.get(agent_id, 0.0) + w * mw

    # Normalize weights
    w_sum = sum(merged_weights.values())
    if w_sum > 0:
        merged_weights = {k: v / w_sum for k, v in merged_weights.items()}

    # Merge priors and penalties (weighted average)
    prior = sum(inp.prior_logodds * mw for inp, mw in zip(inputs, merge_weights))
    penalty = sum(inp.regime_penalty * mw for inp, mw in zip(inputs, merge_weights))

    return CoherenceInput(
        agent_logodds=merged_logodds,
        agent_weights=merged_weights,
        prior_logodds=prior,
        regime_penalty=penalty,
        L_max=L_max,
    )
