# @module: aevara.tests.unit.execution.test_lifecycle
# @deps: aevara.src.execution.lifecycle
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para OrderLifecycle: state transitions, invalid moves,
#           idempotency, terminal states, fill tracking.

from __future__ import annotations

import time

import pytest

from aevara.src.execution.lifecycle import (
    OrderLifecycle,
    OrderPayload,
    OrderState,
    TERMINAL_STATES,
    ALLOWED_TRANSITIONS,
    generate_order_id,
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


def make_lifecycle(**payload_overrides) -> OrderLifecycle:
    return OrderLifecycle(make_payload(**payload_overrides))


# === HAPPY PATH TRANSITIONS ===
class TestHappyPathTransitions:
    def test_starts_created(self):
        lc = make_lifecycle()
        assert lc.state == OrderState.CREATED

    def test_created_to_submitted(self):
        lc = make_lifecycle()
        t = lc.submit()
        assert lc.state == OrderState.SUBMITTED
        assert t.from_state == OrderState.CREATED
        assert t.to_state == OrderState.SUBMITTED

    def test_submitted_to_acknowledged(self):
        lc = make_lifecycle()
        lc.submit()
        t = lc.acknowledge()
        assert lc.state == OrderState.ACKNOWLEDGED
        assert t.to_state == OrderState.ACKNOWLEDGED

    def test_acknowledged_to_partial_fill(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        t = lc.partial_fill(0.5, 50000.0)
        assert lc.state == OrderState.PARTIAL_FILL
        assert lc.filled_qty == pytest.approx(0.5)
        assert lc.avg_fill_price == pytest.approx(50000.0)

    def test_partial_fill_to_filled(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.5, 50000.0)
        t = lc.fill(0.5, 50000.0)
        assert lc.state == OrderState.FILLED
        assert lc.filled_qty == pytest.approx(1.0)

    def test_created_to_cancelled(self):
        lc = make_lifecycle()
        lc.cancel()
        assert lc.state == OrderState.CANCELLED

    def test_created_to_expired(self):
        lc = make_lifecycle()
        lc.expire()
        assert lc.state == OrderState.EXPIRED

    def test_submitted_to_rejected(self):
        lc = make_lifecycle()
        lc.submit()
        lc.reject("Risk limit")
        assert lc.state == OrderState.REJECTED

    def test_submitted_to_cancelled(self):
        lc = make_lifecycle()
        lc.submit()
        lc.cancel()
        assert lc.state == OrderState.CANCELLED


# === INVALID TRANSITIONS ===
class TestInvalidTransitions:
    def test_filled_is_terminal(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.fill(1.0, 50000.0)
        assert lc.is_terminal
        with pytest.raises(AssertionError):
            lc.cancel()

    def test_cancelled_is_terminal(self):
        lc = make_lifecycle()
        lc.cancel()
        assert lc.is_terminal
        with pytest.raises(AssertionError):
            lc.submit()

    def test_rejected_is_terminal(self):
        lc = make_lifecycle()
        lc.submit()
        lc.reject()
        assert lc.is_terminal
        with pytest.raises(AssertionError):
            lc.acknowledge()

    def test_expired_is_terminal(self):
        lc = make_lifecycle()
        lc.expire()
        assert lc.is_terminal
        with pytest.raises(AssertionError):
            lc.submit()

    def test_created_cannot_go_to_filled(self):
        lc = make_lifecycle()
        with pytest.raises(AssertionError):
            lc.fill(1.0, 50000.0)

    def test_cannot_skip_acknowledgement(self):
        lc = make_lifecycle()
        lc.submit()
        with pytest.raises(AssertionError):
            lc.fill(1.0, 50000.0)

    def test_invalid_transition_error_message(self):
        lc = make_lifecycle()
        with pytest.raises(AssertionError, match="Invalid transition"):
            lc.fill(1.0, 50000.0)


# === IDEMPOTENCY ===
class TestIdempotency:
    def test_reapply_same_state_returns_existing_transition(self):
        lc = make_lifecycle()
        t1 = lc.submit()
        t2 = lc.transition_to(OrderState.SUBMITTED)
        assert t1 == t2


# === FILL TRACKING ===
class TestFillTracking:
    def test_average_fill_price_weighted(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.partial_fill(0.5, 49000.0)
        lc.partial_fill(0.5, 51000.0)
        assert lc.filled_qty == pytest.approx(1.0)
        assert lc.avg_fill_price == pytest.approx(50000.0)

    def test_multiple_partial_fills(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        for i in range(4):
            lc.partial_fill(0.25, 50000.0)
        assert lc.filled_qty == pytest.approx(1.0)


# === TRANSITIONS LOG ===
class TestTransitionsLog:
    def test_transitions_captured(self):
        lc = make_lifecycle()
        lc.submit()
        lc.acknowledge()
        lc.fill(1.0, 50000.0)
        transitions = lc.transitions
        assert len(transitions) == 3

    def test_state_dict_complete(self):
        lc = make_lifecycle()
        d = lc.get_state_dict()
        assert d["order_id"] == "test-001"
        assert d["state"] == "CREATED"
        assert d["is_terminal"] is False
        assert d["filled_qty"] == 0.0
        assert d["symbol"] == "BTC/USD"
        assert d["venue"] == "binance"


# === ORDER ID GENERATION ===
class TestOrderIdGeneration:
    def test_generates_unique_id(self):
        id1 = generate_order_id()
        id2 = generate_order_id()
        assert id1 != id2

    def test_valid_uuid_format(self):
        order_id = generate_order_id()
        parts = order_id.split("-")
        assert len(parts) == 5


# === PAYLOAD VALIDATION ===
class TestPayloadValidation:
    def test_negative_size_raises(self):
        with pytest.raises(AssertionError, match="Size must be positive"):
            make_payload(size=-1.0)

    def test_invalid_side_raises(self):
        with pytest.raises(AssertionError, match="Invalid side"):
            make_payload(side="BOTH")

    def test_invalid_order_type_raises(self):
        with pytest.raises(AssertionError, match="Invalid order_type"):
            make_payload(order_type="STOP_LOSS")

    def test_negative_tce_raises(self):
        with pytest.raises(AssertionError, match="TCE budget"):
            make_payload(tce_budget_bps=-1.0)


# === ALLOWED TRANSITIONS MAP ===
class TestTransitionMap:
    def test_all_states_have_mapping(self):
        for state in OrderState:
            assert state in ALLOWED_TRANSITIONS

    def test_terminal_states_empty(self):
        for ts in (OrderState.FILLED, OrderState.CANCELLED,
                   OrderState.REJECTED, OrderState.EXPIRED):
            assert ALLOWED_TRANSITIONS[ts] == set()

    def test_created_allowed_next_states(self):
        assert OrderState.SUBMITTED in ALLOWED_TRANSITIONS[OrderState.CREATED]
        assert OrderState.CANCELLED in ALLOWED_TRANSITIONS[OrderState.CREATED]
        assert OrderState.EXPIRED in ALLOWED_TRANSITIONS[OrderState.CREATED]
