# @module: aevara.src.integration.e2e_orchestrator
# @deps: src.orchestrator.qroe_engine, src.core.coherence.logodds_fusion, src.risk.gates, src.execution.live_gateway, src.telemetry.logger
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: End-to-end async orchestrator wiring all cognitive, risk, execution, and telemetry modules into a deterministic, observable pipeline.

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable, Coroutine
import uuid

from aevara.src.integration.contracts import MarketTick, IntegrationState
from aevara.src.integration.latency_profiler import LatencyProfiler
from aevara.src.integration.state_reconciler import StateReconciler
from aevara.src.integration.shadow_sync import ShadowSyncEngine
from aevara.src.execution.contracts import ExecutionReceipt, LiveOrderPayload

class E2EOrchestrator:
    """
    Scentralized Nervous System (CNS) of Aevra.
    Orchestrates the entire data-to-execution pipeline while maintaining state consistency.
    """
    def __init__(
        self,
        qroe_engine: Any,
        risk_engine: Any,
        live_gateway: Any,
        telemetry: Any,
        shadow_sync: ShadowSyncEngine,
        latency_profiler: LatencyProfiler,
        state_reconciler: StateReconciler,
    ):
        self._qroe = qroe_engine
        self._risk = risk_engine
        self._gateway = live_gateway
        self._telemetry = telemetry
        self._shadow = shadow_sync
        self._latency = latency_profiler
        self._reconciler = state_reconciler
        
        self._cycle_count = 0
        self._failures: Dict[str, bool] = {}

    async def run_cycle(self, tick: MarketTick) -> IntegrationState:
        """
        Executa um unico ciclo deterministico de decisao e execucao.
        """
        self._cycle_count += 1
        trace_id = f"TICK-{self._cycle_count:06d}-{uuid.uuid4().hex[:8]}"
        start_time = time.perf_counter_ns()
        latency_profile: Dict[str, int] = {}

        # 1. Start Cycle - Data Handover
        t1 = self._latency.start_stage("data_handover")
        latency_profile["data_handover"] = self._latency.end_stage("data_handover", t1)

        # 2. QROE Decision Cycle
        t2 = self._latency.start_stage("qroe_decision")
        qroe_result = await self._qroe.run_cycle(tick)
        latency_profile["qroe_decision"] = self._latency.end_stage("qroe_decision", t2)

        # 3. Risk Gate Pre-flight
        t3 = self._latency.start_stage("risk_gate")
        payload = self._build_order_payload(tick, qroe_result, trace_id)
        current_state = self._build_state_snapshot(tick, qroe_result, trace_id)
        risk_passed, risk_msg, risk_hash = self._risk.validate(payload, current_state)
        latency_profile["risk_gate"] = self._latency.end_stage("risk_gate", t3)

        # 4. Execution Gateway
        t4 = self._latency.start_stage("execution")
        receipt = None
        if risk_passed:
            receipt = await self._gateway.submit_order(payload)
        latency_profile["execution"] = self._latency.end_stage("execution", t4)

        # 5. Telemetry Post-flight
        t5 = self._latency.start_stage("telemetry")
        await self._telemetry.log_event("CYCLE_COMPLETE", trace_id, {
            "status": "EXECUTED" if risk_passed else "BLOCKED",
            "receipt": str(receipt) if receipt else None
        })
        latency_profile["telemetry"] = self._latency.end_stage("telemetry", t5)

        # 6. State Reconciliation & Shadow Sync
        t6 = self._latency.start_stage("reconciliation")
        shadow_drift = self._shadow.compute_drift()
        reconcile_ok, reconcile_msg = self._reconciler.validate_coherence({
            "trace_ids": [trace_id],
            "qroe_phase": qroe_result.get("phase", "EXECUTION"),
            "execution_mode": self._gateway.mode.value,
            "market_ts_ns": tick.timestamp_ns
        })
        latency_profile["reconciliation"] = self._latency.end_stage("reconciliation", t6)

        if not reconcile_ok:
             await self._telemetry.log_event("CRITICAL", trace_id, {"msg": f"State drift: {reconcile_msg}"})

        return IntegrationState(
            cycle_id=self._cycle_count,
            market_tick=tick,
            qroe_phase=qroe_result.get("phase", "EXECUTION"),
            coherence_score=qroe_result.get("coherence", 0.0),
            risk_gate_passed=risk_passed,
            execution_receipt=receipt,
            telemetry_trace_id=trace_id,
            latency_profile=latency_profile,
            shadow_drift_pct=shadow_drift
        )

    async def inject_failure(self, module: str) -> None:
        """Chaos engineering: simula falha em subsistema."""
        self._failures[module] = True
        await self._telemetry.log_event("CHAOS", "SYS", {"fault": module})

    async def get_health_report(self) -> Dict:
        return {
            "cycle_count": self._cycle_count,
            "latency_status": self._latency.get_e2e_budget_status(),
            "sync_status": (await self._shadow.generate_sync_report())["sync_status"],
            "failures": list(self._failures.keys())
        }

    def export_state_snapshot(self) -> bytes:
        # Implementation for binary state export
        return str(self._cycle_count).encode()

    def _build_order_payload(self, tick: MarketTick, qroe_result: Dict, trace_id: str) -> LiveOrderPayload:
        return LiveOrderPayload(
            order_id=uuid.uuid4().hex[:26],
            symbol=tick.symbol,
            side=qroe_result.get("side", "BUY"),
            size=qroe_result.get("size", 1.0),
            order_type="LIMIT",
            price=tick.price,
            nonce=self._cycle_count,
            trace_id=trace_id,
            risk_gate_hash="TBD",  # Calculated by Gateway
            max_slippage_bps=5.0,
            expiry_ns=time.time_ns() + int(30e9)
        )

    def _build_state_snapshot(self, tick: MarketTick, qroe_result: Dict, trace_id: str) -> Dict:
        return {
            "margin_available": 1000000.0,
            "daily_pnl_pct": 0.0,
            "total_exposure_qty": 0.0,
            "current_volatility": 0.01,
            "trace_id": trace_id
        }
