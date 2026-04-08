# @module: aevara.src.core.invariants
# @deps: aevara.src.utils.math, aevara.src.utils.logging
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Architectural invariant checks (Phi0-Phi12). Every module that outputs
#           a signal must validate against these before integration.
#           Violations are logged as P0 bugs.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aevara.src.utils.math import clip, safe_log


@dataclass(frozen=True, slots=True)
class InvariantResult:
    """Result of invariant validation."""
    invariant_id: str
    name: str
    passed: bool
    value: float
    threshold: float
    detail: str = ""


def validate_coherence_invariants(L_total: float, input_obj: Any) -> List[InvariantResult]:
    """
    Validate coherence fusion invariants:
    - INV-1: L_total is finite (not NaN/Inf)
    - INV-2: L_total within [-L_max, L_max]
    - INV-3: Agent weights sum to ~1.0
    - INV-4: No individual L_i exceeds L_max
    """
    results = []
    L_max = getattr(input_obj, "L_max", 4.5)

    # INV-1: Finiteness
    is_finite = bool(abs(L_total) < float("inf"))
    results.append(InvariantResult(
        invariant_id="INV-1",
        name="L_total is finite",
        passed=is_finite,
        value=L_total,
        threshold=float("inf"),
        detail="L_total must be finite (not NaN/Inf)" if not is_finite else "",
    ))

    # INV-2: Bounds
    in_bounds = abs(L_total) <= L_max
    results.append(InvariantResult(
        invariant_id="INV-2",
        name="L_total within bounds",
        passed=in_bounds,
        value=L_total,
        threshold=L_max,
        detail=f"|L_total|={abs(L_total):.4f} > L_max={L_max}" if not in_bounds else "",
    ))

    # INV-3: Weight normalization
    agent_weights = getattr(input_obj, "agent_weights", {})
    weight_sum = sum(agent_weights.values()) if agent_weights else 0.0
    weights_ok = abs(weight_sum - 1.0) < 1e-6
    results.append(InvariantResult(
        invariant_id="INV-3",
        name="Agent weights sum to 1.0",
        passed=weights_ok,
        value=weight_sum,
        threshold=1.0,
        detail=f"Weight sum={weight_sum:.10f}" if not weights_ok else "",
    ))

    # INV-4: Individual bounds
    agent_logodds = getattr(input_obj, "agent_logodds", {})
    individual_ok = all(abs(v) <= L_max for v in agent_logodds.values()) if agent_logodds else True
    results.append(InvariantResult(
        invariant_id="INV-4",
        name="Individual L_i within bounds",
        passed=individual_ok,
        value=max(abs(v) for v in agent_logodds.values()) if agent_logodds else 0.0,
        threshold=L_max,
        detail=f"Some L_i exceeds L_max={L_max}" if not individual_ok else "",
    ))

    return results


def validate_data_invariants(tick_data: Dict[str, Any]) -> List[InvariantResult]:
    """
    Validate data pipeline invariants:
    - INV-5: Timestamp is positive and monotonic
    - INV-6: bid < ask (positive spread)
    - INV-7: All required fields present
    - INV-8: Checksum is valid (8 hex chars)
    """
    # TODO: implement when tick data structure is defined
    return []


def aggregate_invariants(results: List[InvariantResult]) -> bool:
    """Return True if ALL invariants pass."""
    return all(r.passed for r in results)


def format_invariant_report(results: List[InvariantResult]) -> str:
    """Format invariant results for logging."""
    lines = ["== Invariant Validation Report =="]
    all_pass = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            all_pass = False
        lines.append(f"  [{status}] {r.invariant_id}: {r.name} | value={r.value:.6f} | threshold={r.threshold}")
        if r.detail:
            lines.append(f"         Detail: {r.detail}")
    lines.append(f"Overall: {'ALL PASS' if all_pass else 'FAILURE - REVERT REQUIRED'}")
    return "\n".join(lines)
