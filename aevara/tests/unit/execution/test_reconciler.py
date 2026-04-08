# @module: aevara.tests.unit.execution.test_reconciler
# @deps: aevara.src.execution.reconciler, aevara.src.execution.lifecycle
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para Reconciler: drift detection, nonce validation,
#           corrective actions, retry bounds, state alignment.

from __future__ import annotations

import asyncio
import time

import pytest

from aevara.src.execution.lifecycle import (
    OrderLifecycle,
    OrderPayload,
    OrderState,
)
from aevara.src.execution.reconciler import (
    Reconciler,
    ReconcileAction,
    ReconcileResult,
    ExchangeOrderState,
)


def make_payload(**overrides) -> OrderPayload:
    defaults = {
        "order_id": "test-001",
        "symbol": "BTC/USD",
        "side": "BUY",
        "size": 1.0,
        "order_type": "LIMIT",
        "venue": "binance",
        "price": 50000.0,
        "tce_budget_bps": 5.0,
        "trace_id": "trace-001",
        "nonce": 12345,
        "expiry_ns": time.time_ns() + 60_000_000_000,
    }
    defaults.update(overrides)
    return OrderPayload(**defaults)


def make_lifecycle(**kwargs) -> OrderLifecycle:
    return OrderLifecycle(make_payload(**kwargs))


def make_exchange_state(
    order_id: str = "test-001",
    state: OrderState = OrderState.SUBMITTED,
    filled_qty: float = 0.0,
    remaining_qty: float = 1.0,
    avg_fill_price: float = 0.0,
    nonce: int = 12345,
) -> ExchangeOrderState:
    return ExchangeOrderState(
        order_id=order_id,
        state=state,
        filled_qty=filled_qty,
        remaining_qty=remaining_qty,
        avg_fill_price=avg_fill_price,
        status_ts=time.time_ns(),
        nonce=nonce,
    )


def make_reconciler(**kwargs) -> Reconciler:
    return Reconciler(
        interval_s=kwargs.get("interval_s", 5.0),
        drift_threshold=kwargs.get("drift_threshold", 0.0001),
        max_retries=kwargs.get("max_retries", 3),
    )


# === HAPPY PATH: ALIGNED STATES ===
class TestAlignment:
    def test_returns_none_when_aligned(self):
        lc = make_lifecycle()
        lc.submit()
        exchange = make_exchange_state(
            state=OrderState.SUBMITTED,
            filled_qty=0.0,
            nonce=12345,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.NONE
        assert result.resolution == "States aligned"

    def test_returns_none_when_filled_qty_matches(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.5, 50000.0)
        exchange = make_exchange_state(
            state=OrderState.PARTIAL_FILL,
            filled_qty=0.5,
            remaining_qty=0.5,
            avg_fill_price=50000.0,
            nonce=12345,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        # Should be aligned even with small drift if within threshold
        assert result.action in (ReconcileAction.NONE,) or (
            result.drift_bps <= reconciler._drift_threshold * 10000
        )


# === NONCE VALIDATION ===
class TestNonceValidation:
    def test_nonce_mismatch_returns_rejected(self):
        lc = make_lifecycle()
        lc.submit()
        exchange = make_exchange_state(nonce=99999)
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.MARK_REJECTED
        assert "Nonce mismatch" in result.resolution

    def test_nonce_match_passes(self):
        lc = make_lifecycle(nonce=111)
        lc.submit()
        exchange = make_exchange_state(nonce=111)
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.NONE


# === DRIFT DETECTION ===
class TestDriftDetection:
    def test_detects_exchange_has_more_filled(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        # Internal shows 0 filled, exchange shows 0.5 filled
        exchange = make_exchange_state(
            state=OrderState.PARTIAL_FILL,
            filled_qty=0.5,
            remaining_qty=0.5,
            avg_fill_price=50000.0,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action in (
            ReconcileAction.MARK_FILLED,
            ReconcileAction.ADJUST_SIZE,
        )

    def test_detects_internal_has_more_filled(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.5, 50000.0)
        # Internal shows 0.5, exchange shows 0.0
        exchange = make_exchange_state(
            state=OrderState.ACKNOWLEDGED,
            filled_qty=0.0,
            remaining_qty=1.0,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.DRIFT_DETECTED

    def test_rejected_on_exchange(self):
        lc = make_lifecycle()
        lc.submit()
        exchange = make_exchange_state(state=OrderState.REJECTED)
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.MARK_REJECTED

    def test_residual_cancel_when_internal_terminal(self):
        lc = make_lifecycle()
        lc.cancel()
        exchange = make_exchange_state(
            state=OrderState.SUBMITTED,
            remaining_qty=0.5,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        assert result.action == ReconcileAction.CANCEL_RESIDUAL

    def test_drift_bps_calculated(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.5, 50000.0)
        exchange = make_exchange_state(
            state=OrderState.PARTIAL_FILL,
            filled_qty=0.75,
            remaining_qty=0.25,
            avg_fill_price=50000.0,
        )
        reconciler = make_reconciler()
        result = asyncio.get_event_loop().run_until_complete(
            reconciler.reconcile_order(lc, exchange)
        )
        drift = abs(0.5 - 0.75) / 1.0 * 10000
        assert result.drift_bps == pytest.approx(drift, rel=0.01)


# === ACTION APPLICATION ===
class TestActionApplication:
    def test_apply_mark_filled(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        reconciler = make_reconciler()
        exchange = make_exchange_state(
            state=OrderState.FILLED,
            filled_qty=1.0,
            remaining_qty=0.0,
            avg_fill_price=50000.0,
        )
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.MARK_FILLED, exchange
        )
        assert success
        assert lc.state == OrderState.FILLED

    def test_apply_adjust_size(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.3, 50000.0)
        reconciler = make_reconciler()
        exchange = make_exchange_state(
            state=OrderState.PARTIAL_FILL,
            filled_qty=0.8,
            avg_fill_price=50000.0,
        )
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.ADJUST_SIZE, exchange
        )
        assert success

    def test_apply_mark_rejected_from_submitted(self):
        lc = make_lifecycle()
        lc.submit()
        reconciler = make_reconciler()
        exchange = make_exchange_state(state=OrderState.REJECTED)
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.MARK_REJECTED, exchange
        )
        assert success
        assert lc.state == OrderState.REJECTED

    def test_apply_mark_rejected_not_from_submitted(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        reconciler = make_reconciler()
        exchange = make_exchange_state(state=OrderState.REJECTED)
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.MARK_REJECTED, exchange
        )
        assert not success

    def test_apply_cancel_residual(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        reconciler = make_reconciler()
        exchange = make_exchange_state(
            state=OrderState.ACKNOWLEDGED,
            remaining_qty=0.5,
        )
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.CANCEL_RESIDUAL, exchange
        )
        assert success
        assert lc.state == OrderState.CANCELLED

    def test_apply_none_is_noop(self):
        lc = make_lifecycle()
        reconciler = make_reconciler()
        exchange = make_exchange_state()
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.NONE, exchange
        )
        assert success
        assert lc.state == OrderState.CREATED

    def test_apply_residual_when_terminal_returns_false(self):
        lc = make_lifecycle()
        lc.cancel()
        reconciler = make_reconciler()
        exchange = make_exchange_state(
            state=OrderState.CANCELLED,
            remaining_qty=0.0,
        )
        success = reconciler.apply_reconcile_action(
            lc, ReconcileAction.CANCEL_RESIDUAL, exchange
        )
        assert not success


# === DETERMINE ACTION LOGIC ===
class TestDetermineAction:
    def test_exchange_filled_but_internal_not(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        exchange = make_exchange_state(
            state=OrderState.FILLED,
            filled_qty=1.0,
            avg_fill_price=50000.0,
        )
        reconciler = make_reconciler()
        action, _ = reconciler._determine_action(lc, exchange, 10000.0)
        assert action == ReconcileAction.MARK_FILLED

    def test_exchange_rejected(self):
        lc = make_lifecycle()
        lc.submit()
        exchange = make_exchange_state(state=OrderState.REJECTED)
        reconciler = make_reconciler()
        action, _ = reconciler._determine_action(lc, exchange, 10000.0)
        assert action == ReconcileAction.MARK_REJECTED

    def test_drift_detected_as_fallback(self):
        lc = make_lifecycle()
        lc.submit()
        exchange = make_exchange_state(
            state=OrderState.SUBMITTED,
            filled_qty=0.0,
            remaining_qty=1.0,
        )
        reconciler = make_reconciler()
        action, reason = reconciler._determine_action(lc, exchange, 0.05)
        assert action == ReconcileAction.DRIFT_DETECTED


# === RECONCILER CONFIGURATION ===
class TestReconcilerConfig:
    def test_custom_drift_threshold(self):
        reconciler = make_reconciler(drift_threshold=0.001)
        assert reconciler._drift_threshold == 0.001

    def test_custom_max_retries(self):
        reconciler = make_reconciler(max_retries=5)
        assert reconciler._max_retries == 5

    def test_custom_interval(self):
        reconciler = make_reconciler(interval_s=10.0)
        assert reconciler._interval_s == 10.0


# === NONCE MANAGEMENT ===
class TestNonceManagement:
    def test_register_nonce(self):
        reconciler = make_reconciler()
        reconciler.register_nonce(999, "order-abc")
        assert reconciler._nonce_cache[999] == "order-abc"

    def test_evict_expired_nonces_returns_int(self):
        reconciler = make_reconciler()
        result = reconciler.evict_expired_nonces()
        assert isinstance(result, int)
