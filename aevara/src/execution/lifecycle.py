# @module: aevara.src.execution.lifecycle
# @deps: time, dataclasses, enum, typing, uuid
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Strict order state machine with idempotent transitions,
#           allowed transition enforcement, lifecycle tracking.
#           Zero state drift, zero invalid transitions.

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# Strict transition map: state -> set of allowed next states
ALLOWED_TRANSITIONS: Dict[OrderState, Set[OrderState]] = {
    OrderState.CREATED: {OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.CANCELLED},
    OrderState.ACKNOWLEDGED: {OrderState.PARTIAL_FILL, OrderState.FILLED, OrderState.CANCELLED},
    OrderState.PARTIAL_FILL: {OrderState.PARTIAL_FILL, OrderState.FILLED, OrderState.CANCELLED},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
    OrderState.EXPIRED: set(),
}

TERMINAL_STATES = {OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED}


@dataclass(frozen=True, slots=True)
class OrderPayload:
    """Immutable order definition with validation."""
    order_id: str
    symbol: str
    side: str  # BUY/SELL
    size: float
    order_type: str  # LIMIT/MARKET/IOC/FOK/POST_ONLY
    venue: str
    price: Optional[float]
    tce_budget_bps: float
    trace_id: str
    nonce: int
    expiry_ns: int

    def __post_init__(self):
        assert self.size > 0, "Size must be positive"
        assert self.tce_budget_bps >= 0, "TCE budget cannot be negative"
        assert self.side in ("BUY", "SELL"), f"Invalid side: {self.side}"
        assert self.order_type in ("LIMIT", "MARKET", "IOC", "FOK", "POST_ONLY"), \
            f"Invalid order_type: {self.order_type}"


@dataclass(frozen=True, slots=True)
class OrderTransition:
    """Registro auditavel de transicao de estado."""
    order_id: str
    from_state: OrderState
    to_state: OrderState
    reason: str
    ts_ns: int
    metadata: Dict[str, Any]


class OrderLifecycle:
    """
    Maquina de estados de ordem com transicoes estritas.

    Invariantes:
    - Transicoes so permitidas via ALLOWED_TRANSITIONS
    - Estados terminais nao permitem mais transicoes
    - Registro completo de todas as transicoes
    - Idempotente: re-aplicar mesma transicao sem efeito
    """

    def __init__(self, payload: OrderPayload):
        self._payload = payload
        self._state = OrderState.CREATED
        self._transitions: List[OrderTransition] = []
        self._filled_qty = 0.0
        self._avg_fill_price = 0.0
        self._created_at_ns = time.time_ns()

    @property
    def state(self) -> OrderState:
        return self._state

    @property
    def payload(self) -> OrderPayload:
        return self._payload

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    @property
    def filled_qty(self) -> float:
        return self._filled_qty

    @property
    def avg_fill_price(self) -> float:
        return self._avg_fill_price

    @property
    def transitions(self) -> List[OrderTransition]:
        return list(self._transitions)

    @property
    def order_id(self) -> str:
        return self._payload.order_id

    def transition_to(
        self,
        new_state: OrderState,
        reason: str = "",
        fill_qty: float = 0.0,
        fill_price: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrderTransition:
        """
        Executa transicao de estado com validacao estrita.

        Raises:
            AssertionError: Se transicao nao e permitida.
        """
        # Idempotency: if already in target state and no fill data, return existing transition
        if new_state == self._state and fill_qty == 0:
            return self._transitions[-1] if self._transitions else OrderTransition(
                order_id=self._payload.order_id,
                from_state=self._state,
                to_state=new_state,
                reason=reason or "No change",
                ts_ns=__import__('time').time_ns(),
                metadata={},
            )

        # Same state with new fill data -> allow PARTIAL_FILL -> PARTIAL_FILL

        allowed = ALLOWED_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise AssertionError(
                f"Invalid transition {self._state.value} -> {new_state.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        transition = self._make_transition(new_state, reason, metadata)
        self._transitions.append(transition)
        self._state = new_state

        # Update fill tracking
        if new_state in (OrderState.PARTIAL_FILL, OrderState.FILLED) and fill_qty > 0:
            total_notional = self._avg_fill_price * self._filled_qty + fill_price * fill_qty
            self._filled_qty += fill_qty
            self._avg_fill_price = total_notional / self._filled_qty

        return transition

    def _make_transition(
        self,
        new_state: OrderState,
        reason: str,
        metadata: Optional[Dict[str, Any]],
    ) -> OrderTransition:
        return OrderTransition(
            order_id=self._payload.order_id,
            from_state=self._state,
            to_state=new_state,
            reason=reason,
            ts_ns=time.time_ns(),
            metadata=metadata or {},
        )

    def submit(self) -> OrderTransition:
        """CREATED -> SUBMITTED"""
        return self.transition_to(OrderState.SUBMITTED, reason="Submitted to venue")

    def acknowledge(self) -> OrderTransition:
        """SUBMITTED -> ACKNOWLEDGED"""
        return self.transition_to(OrderState.ACKNOWLEDGED, reason="Venue acknowledged")

    def reject(self, reason: str = "Rejected by venue") -> OrderTransition:
        """SUBMITTED -> REJECTED"""
        return self.transition_to(OrderState.REJECTED, reason=reason)

    def partial_fill(self, qty: float, price: float) -> OrderTransition:
        """ACKNOWLEDGED/PARTIAL_FILL -> PARTIAL_FILL"""
        return self.transition_to(
            OrderState.PARTIAL_FILL,
            reason=f"Partial fill: {qty} @ {price}",
            fill_qty=qty,
            fill_price=price,
        )

    def fill(self, qty: float, price: float) -> OrderTransition:
        """ACKNOWLEDGED/PARTIAL_FILL -> FILLED"""
        return self.transition_to(
            OrderState.FILLED,
            reason=f"Filled: {qty} @ {price}",
            fill_qty=qty,
            fill_price=price,
        )

    def cancel(self, reason: str = "User cancelled") -> OrderTransition:
        """Any non-terminal -> CANCELLED (if allowed)"""
        return self.transition_to(OrderState.CANCELLED, reason=reason)

    def expire(self) -> OrderTransition:
        """CREATED -> EXPIRED"""
        return self.transition_to(OrderState.EXPIRED, reason="Order expired (TTL)")

    def is_expired(self) -> bool:
        """Check if order has exceeded TTL."""
        if self._payload.expiry_ns <= 0:
            return False
        return time.time_ns() > self._payload.expiry_ns

    def get_state_dict(self) -> Dict[str, Any]:
        """Retorna snapshot completo do estado."""
        return {
            "order_id": self._payload.order_id,
            "state": self._state.value,
            "is_terminal": self.is_terminal,
            "filled_qty": self._filled_qty,
            "avg_fill_price": self._avg_fill_price,
            "n_transitions": len(self._transitions),
            "symbol": self._payload.symbol,
            "side": self._payload.side,
            "venue": self._payload.venue,
        }


def generate_order_id() -> str:
    """Gera order_id no formato UUID v4 (26 chars with hyphens = 36)."""
    return str(uuid.uuid4())
