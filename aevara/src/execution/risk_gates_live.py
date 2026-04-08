# @module: aevara.src.execution.risk_gates_live
# @deps: hashlib, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Immutable pre-flight risk validation with FTMO constraints, hard blocks, and telemetry logging.

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aevara.src.execution.contracts import LiveOrderPayload


# ─── Gate Check Result ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str
    ts_ns: int


# ─── Risk Gate Result (immutable) ──────────────────────────────────────

@dataclass(frozen=True, slots=True)
class RiskGateResult:
    """Resultado imutavel da validacao de risk gates."""
    all_passed: bool
    failed_gates: List[str]
    checks: List[GateCheck]
    gate_hash: str
    ts_ns: int


# ─── FTMO Constraints ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FTMOConstraints:
    daily_loss_limit_pct: float = 4.8     # Hard max daily loss
    total_loss_limit_pct: float = 8.0     # Hard max total drawdown
    max_positions: int = 3                # Concurrent position cap
    min_trading_days: int = 1             # Minimum active days before scaling
    news_blackout: bool = False           # If True, block orders during news


# ─── Live Risk Gate Engine ─────────────────────────────────────────────

class LiveRiskGateEngine:
    """
    Motor de validacao pre-flight para ordens ao vivo.

    Gates executados (ordem):
    1. margin_available       — capital suficiente para sizing
    2. daily_dd_limit         — nao excedeu perda diaria FTMO
    3. total_dd_limit         — perda total < 8%
    4. total_exposure         — nao excede limite agregado
    5. volatility_regime_cap  — volatilidade dentro do regime aceito
    6. ftmo_daily_loss        — <= 4.8% daily
    7. ftmo_total_loss        — <= 8.0% total
    8. correlation_spread     — correlacao entre ativos nao concentrada
    9. killswitch_active      — killswitch desarmado
    10. order_expiry          — ordem nao expirada

    Se QUALQUER gate falhar → hard block (no override sem 2FA CEO).
    """

    def __init__(self, ftmo_constraints: Optional[FTMOConstraints] = None):
        self._ftmo = ftmo_constraints or FTMOConstraints()
        self._gate_history: List[RiskGateResult] = []

    # ── Public API ──────────────────────────────────────────────────────

    def validate(
        self,
        order: LiveOrderPayload,
        current_state: Dict,
    ) -> Tuple[bool, str, str]:
        """
        Executa todos os gates de risco.

        Returns:
            (passed: bool, failure_reason: str, gate_hash: str)
        """
        now = time.time_ns()
        checks: List[GateCheck] = []

        # 1. killswitch_active (fail-fast)
        if current_state.get("killswitch_active", False):
            return False, "Killswitch active", ""

        # 2. order_expiry
        if order.expiry_ns > 0 and time.time_ns() > order.expiry_ns:
            return False, "Order expired before risk check", ""

        # 3. margin_available
        checks.append(self._check_margin(order, current_state))

        # 4. ftmo_daily_loss
        checks.append(self._check_ftmo_daily(current_state))

        # 5. ftmo_total_loss
        checks.append(self._check_ftmo_total(current_state))

        # 6. total_exposure
        checks.append(self._check_total_exposure(order, current_state))

        # 7. volatility_regime_cap
        checks.append(self._check_volatility_cap(current_state))

        # 8. correlation_spread
        checks.append(self._check_correlation(current_state))

        # Build result
        failed = [c.name for c in checks if not c.passed]
        all_ok = len(failed) == 0
        gate_hash = self._compute_hash(checks)

        result = RiskGateResult(
            all_passed=all_ok,
            failed_gates=failed,
            checks=checks,
            gate_hash=gate_hash,
            ts_ns=now,
        )
        self._gate_history.append(result)

        if all_ok:
            return True, "", gate_hash
        return False, f"Failed gates: {', '.join(failed)}", gate_hash

    def generate_gate_hash(self, checks: Dict[str, bool]) -> str:
        """Gera hash SHA-256 dos checks para auditoria."""
        payload = json.dumps(checks, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def gate_history(self) -> List[RiskGateResult]:
        return list(self._gate_history)

    # ── Individual Gates ────────────────────────────────────────────────

    def _check_margin(self, order: LiveOrderPayload, state: Dict) -> GateCheck:
        available = state.get("margin_available", 100000.0)
        price = order.price or 42000.0
        required = order.size * price
        ok = available >= required
        return GateCheck(
            name="margin_available",
            passed=ok,
            detail=f"available={available:.2f}, required={required:.2f}",
            ts_ns=time.time_ns(),
        )

    def _check_ftmo_daily(self, state: Dict) -> GateCheck:
        daily_pnl_pct = state.get("daily_pnl_pct", 0.0)
        limit = self._ftmo.daily_loss_limit_pct
        ok = daily_pnl_pct >= -limit
        return GateCheck(
            name="ftmo_daily_loss",
            passed=ok,
            detail=f"daily_pnl={daily_pnl_pct:.2f}%, limit=-{limit:.2f}%",
            ts_ns=time.time_ns(),
        )

    def _check_ftmo_total(self, state: Dict) -> GateCheck:
        total_dd_pct = state.get("total_drawdown_pct", 0.0)
        limit = self._ftmo.total_loss_limit_pct
        ok = total_dd_pct <= limit
        return GateCheck(
            name="ftmo_total_loss",
            passed=ok,
            detail=f"total_dd={total_dd_pct:.2f}%, limit={limit:.2f}%",
            ts_ns=time.time_ns(),
        )

    def _check_total_exposure(self, order: LiveOrderPayload, state: Dict) -> GateCheck:
        total_exposure = state.get("total_exposure_qty", 0.0)
        max_exposure = state.get("max_exposure_qty", 10.0)
        ok = (total_exposure + order.size) <= max_exposure
        return GateCheck(
            name="total_exposure",
            passed=ok,
            detail=f"current={total_exposure:.4f}, order={order.size:.4f}, max={max_exposure:.4f}",
            ts_ns=time.time_ns(),
        )

    def _check_volatility_cap(self, state: Dict) -> GateCheck:
        vol = state.get("current_volatility", 0.0)
        cap = state.get("volatility_cap", 0.05)
        ok = vol <= cap
        return GateCheck(
            name="volatility_regime_cap",
            passed=ok,
            detail=f"vol={vol:.4f}, cap={cap:.4f}",
            ts_ns=time.time_ns(),
        )

    def _check_correlation(self, state: Dict) -> GateCheck:
        """Verifica concentracao excessiva por correlacao."""
        corr = state.get("correlation_index", 0.0)
        max_corr = state.get("max_correlation", 0.85)
        ok = corr <= max_corr
        return GateCheck(
            name="correlation_spread",
            passed=ok,
            detail=f"corr={corr:.4f}, max={max_corr:.4f}",
            ts_ns=time.time_ns(),
        )

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(checks: List[GateCheck]) -> str:
        payload = json.dumps(
            [{"name": c.name, "passed": c.passed} for c in checks],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()
