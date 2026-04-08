# @module: aevara.src.utils.math
# @deps: None
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Mathematical primitives for log-odds space, safe numerics, and bounded transforms.
#           All functions are pure (no side effects), deterministic, and invariant-safe.

from __future__ import annotations

import math
from typing import Union

Number = Union[int, float]


def sigmoid(x: float, epsilon: float = 1e-8) -> float:
    """
    Logistic sigmoid: sigma(x) = 1 / (1 + exp(-x))
    Numerically stable: uses exp(x) / (1 + exp(x)) for x < 0.
    Output clipped to [epsilon, 1 - epsilon] to avoid log-domain singularities.

    Args:
        x: Real-valued input (unbounded log-odds)
        epsilon: Safety margin from boundaries [0, 1]

    Returns:
        float in (epsilon, 1 - epsilon)
    """
    if x >= 0:
        result = 1.0 / (1.0 + math.exp(-x))
    else:
        ex = math.exp(x)
        result = ex / (1.0 + ex)
    return clip(result, epsilon, 1.0 - epsilon)


def logit(p: float, epsilon: float = 1e-8) -> float:
    """
    Logit transform: logit(p) = log(p / (1 - p))
    Input is clipped to [epsilon, 1 - epsilon] to avoid log(0).

    Args:
        p: Probability value in [0, 1]
        epsilon: Safety margin from boundaries

    Returns:
        float in R (unbounded log-odds)
    """
    p = clip(p, epsilon, 1.0 - epsilon)
    return math.log(p / (1.0 - p))


def clip(x: float, min_val: float, max_val: float) -> float:
    """
    Clip value to [min_val, max_val]. Invariant: min_val <= max_val.

    Args:
        x: Input value
        min_val: Lower bound
        max_val: Upper bound

    Returns:
        Clipped value

    Raises:
        ValueError: If min_val > max_val
    """
    if min_val > max_val:
        raise ValueError(f"clip: min_val ({min_val}) > max_val ({max_val})")
    if x < min_val:
        return min_val
    if x > max_val:
        return max_val
    return x


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    """
    Safe division: returns default if divisor is zero.

    Args:
        a: Numerator
        b: Denominator
        default: Value to return when b == 0

    Returns:
        a / b if b != 0, else default
    """
    if b == 0.0:
        return default
    return a / b


def safe_log(x: float, epsilon: float = 1e-12) -> float:
    """
    Safe logarithm: log(max(x, epsilon)).

    Args:
        x: Input value
        epsilon: Minimum value to prevent log(0)

    Returns:
        log(max(x, epsilon))
    """
    return math.log(max(x, epsilon))


def softmax(x: list[float]) -> list[float]:
    """
    Numerically stable softmax: softmax(x_i) = exp(x_i - max(x)) / sum(exp(x - max(x)))

    Args:
        x: List of real values

    Returns:
        List of probabilities summing to 1.0
    """
    if not x:
        return []
    max_x = max(x)
    exps = [math.exp(xi - max_x) for xi in x]
    sum_exps = sum(exps)
    return [e / sum_exps for e in exps]


def weighted_sum(values: list[float], weights: list[float]) -> float:
    """
    Weighted sum: sum(v_i * w_i). Caller must ensure len(values) == len(weights).

    Args:
        values: Input values
        weights: Weights (not required to sum to 1)

    Returns:
        Float weighted sum
    """
    return sum(v * w for v, w in zip(values, weights))
