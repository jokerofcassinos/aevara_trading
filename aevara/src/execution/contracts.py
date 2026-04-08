# @module: aevara.src.execution.contracts
# @deps: dataclasses, typing
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: Immutable data contracts for live execution, including order payloads and receipts.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class LiveOrderPayload:
    """
    Immutable order definition for live gateway.
    Ensures idempotency via nonce and auditability via risk_gate_hash.
    """
    order_id: str               # ULID/UUIDv7 (26-36 chars)
    symbol: str
    side: str                   # BUY/SELL
    size: float
    order_type: str             # LIMIT/MARKET/IOC/FOK
    price: Optional[float]
    nonce: int                  # Idempotency key (monotonic per session)
    trace_id: str               # Telemetry propagation
    risk_gate_hash: str         # SHA256 of approved risk checks
    max_slippage_bps: float
    expiry_ns: int              # Kill switch timestamp

    def __post_init__(self):
        assert len(self.order_id) in (26, 36), f"Invalid order_id format: {len(self.order_id)}"
        assert self.size > 0, "Size must be positive"
        assert self.max_slippage_bps >= 0, "Slippage budget cannot be negative"
        assert self.side in ("BUY", "SELL"), f"Invalid side: {self.side}"
        assert self.order_type in ("LIMIT", "MARKET", "IOC", "FOK"), \
            f"Unsupported order_type: {self.order_type}"
        assert self.risk_gate_hash != "", "Risk gate hash required"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """
    Immutable execution receipt returned by the live gateway.
    Captures exchange response, latency, and audit data.
    """
    exchange_order_id: str
    status: str                 # FILLED/PARTIAL/CANCELLED/REJECTED/PENDING
    filled_size: float
    filled_price: Optional[float]
    commission_usd: float
    slippage_bps: float
    latency_us: int
    nonce_verified: bool
    risk_gate_passed: bool
    trace_id: str
