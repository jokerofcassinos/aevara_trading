# @module: aevara.src.integration.contracts
# @deps: dataclasses, typing, aevara.src.execution.contracts
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Integration-layer contracts and state snapshots, ensuring consistency cross-module.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from aevara.src.execution.contracts import ExecutionReceipt

@dataclass(frozen=True, slots=True)
class MarketTick:
    symbol: str
    price: float
    bid: float
    ask: float
    volume: float
    timestamp_ns: int
    exchange: str

@dataclass(frozen=True, slots=True)
class IntegrationState:
    cycle_id: int
    market_tick: MarketTick
    qroe_phase: str
    coherence_score: float
    risk_gate_passed: bool
    execution_receipt: Optional[ExecutionReceipt]
    telemetry_trace_id: str
    latency_profile: Dict[str, int]  # stage -> duration_us
    shadow_drift_pct: float
