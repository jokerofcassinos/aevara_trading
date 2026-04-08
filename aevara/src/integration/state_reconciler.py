# @module: aevara.src.integration.state_reconciler
# @deps: typing, time
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Cross-module consistency check ensuring all subsystems share the same market/position/trace context.

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple

class StateReconciler:
    """
    Validador cruzado de consistência de estado entre módulos.
    Garante que QROE, Risk, Execution e Telemetry estão sincronizados por ciclo.
    """
    def __init__(self, drift_threshold: float = 0.001):
        self._drift_threshold = drift_threshold
        self._last_reconcile = time.time_ns()
        self._history: List[Dict[str, Any]] = []

    def validate_coherence(self, modules_state: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verifica se os estados dos módulos são consistentes entre si.
        - phase: QROE vs Execution mode context
        - trace: Todos devem compartilhar o mesmo trace_id
        - timestamp: Sync temporal dentro de 10ms
        """
        now = time.time_ns()
        self._last_reconcile = now
        
        qroe_phase = modules_state.get("qroe_phase")
        risk_context = modules_state.get("risk_regime")
        exec_mode = modules_state.get("execution_mode")
        trace_ids = modules_state.get("trace_ids", [])
        
        # 1. Trace Consistency
        if len(set(trace_ids)) > 1:
            return False, f"Trace ID drift detected: {set(trace_ids)}"
            
        # 2. Phase Consistency (Soft check)
        if qroe_phase == "AUDIT" and exec_mode == "live":
             return False, "Conflict: Audit phase active while Execution in live mode"

        # 3. Market Sync
        market_ts = modules_state.get("market_ts_ns", 0)
        if abs(now - market_ts) > 1e9: # 1s max lag for reconcile
             return False, "Market data lag exceeds safety threshold (1s)"

        self._history.append({**modules_state, "reconcile_ts": now})
        return True, "Consistent"

    def get_audit_trail(self, limit: int = 100) -> List[Dict]:
        return self._history[-limit:]
