# @module: PHASE_GATE_VALIDATOR
# @deps: PROJECT_STATE.yaml, profiles/*.yaml
# @status: INITIALIZED
# @last_update: 2026-04-06
# @summary: Validador de gates de fase (G1-G4) com schema validation

import yaml
import os
import sys
import json
from dataclasses import dataclass
from typing import Dict, List


GATE_CONFIG = {
    "G1": {
        "name": "Schema Integrity",
        "check": "zero schema validation errors",
        "threshold": 0,
        "metric": "SchemaValidationError count in 10k iterations",
    },
    "G2": {
        "name": "Phantom Fidelity",
        "check": "ghost vs real alignment >= 0.82",
        "threshold": 0.82,
        "metric": "corr(RR_ghost, RR_real) in 5 regimes",
    },
    "G3": {
        "name": "Coherence Stability",
        "check": "C2 std < 0.15 during regime shift",
        "threshold": 0.15,
        "metric": "std(C2) during transition",
    },
    "G4": {
        "name": "Risk Gate Efficacy",
        "check": "max drawdown <= 4.8% in 1000 simulations",
        "threshold": 4.8,
        "metric": "max_drawdown %",
    },
}


@dataclass
class GateResult:
    gate_id: str
    name: str
    passed: bool
    value: float
    threshold: float


def validate_gate(gate_id: str, value: float) -> GateResult:
    """Validate a single gate against its threshold."""
    config = GATE_CONFIG.get(gate_id)
    if not config:
        return GateResult(gate_id, "UNKNOWN", False, value, 0)

    if gate_id == "G1":
        passed = value == 0
    elif gate_id == "G4":
        passed = value <= config["threshold"]
    else:
        passed = value >= config["threshold"]

    return GateResult(
        gate_id=gate_id,
        name=config["name"],
        passed=passed,
        value=value,
        threshold=config["threshold"],
    )


def validate_all_gates(gate_values: Dict[str, float]) -> List[GateResult]:
    """Validate all gates 1-4."""
    results = []
    for gid in ["G1", "G2", "G3", "G4"]:
        val = gate_values.get(gid, 0)
        results.append(validate_gate(gid, val))
    return results


def generate_gate_report(results: List[GateResult]) -> str:
    """Generate gate validation report."""
    report = "## Gate Validation Report\n\n"
    all_pass = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            all_pass = False
        report += f"- **{r.gate_id} ({r.name})**: {status} | Value: {r.value:.4f} | Threshold: {r.threshold}\n"
    report += f"\n**Overall**: {'ALL GATES PASSED' if all_pass else 'GATE FAILURE - REVERSION REQUIRED'}\n"
    return report


if __name__ == "__main__":
    sample = {"G1": 0, "G2": 0.85, "G3": 0.92, "G4": 4.2}
    results = validate_all_gates(sample)
    print(generate_gate_report(results))
