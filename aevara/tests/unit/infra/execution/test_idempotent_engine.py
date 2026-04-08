# @module: aevara.tests.unit.infra.execution.test_idempotent_engine
# @deps: aevara.src.infra.execution.idempotent_engine
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para IdempotentEngine: nonce generation, idempotent submit, state updates, TTL eviction.

from __future__ import annotations

import time

import pytest

from aevara.src.infra.execution.idempotent_engine import (
    IdempotentEngine,
    OrderRecord,
    OrderState,
)


# === NONCE GENERATION ===
class TestNonceGeneration:
    def test_generates_unique_nonce(self):
        engine = IdempotentEngine()
        nonce1 = engine.generate_nonce()
        nonce2 = engine.generate_nonce()
        assert nonce1 != nonce2

    def test_nonce_is_uuid_v4_format(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        parts = nonce.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12


# === SUBMIT & IDEMPOTENCY ===
class TestSubmitIdempotency:
    def test_first_submits_returns_pending(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        state, record = engine.submit(nonce, {"symbol": "BTC/USD", "side": "buy"})
        assert state == OrderState.PENDING
        assert record is None

    def test_duplicate_nonce_returns_existing(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD", "side": "buy"})
        state, record = engine.submit(nonce, {"symbol": "ETH/USD", "side": "sell"})
        assert record is not None
        assert record.payload["symbol"] == "BTC/USD"
        assert state == OrderState.PENDING

    def test_update_state_reflects_on_duplicate(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        engine.update_state(nonce, OrderState.FILLED)
        state, record = engine.submit(nonce, {"symbol": "DIFFERENT"})
        assert record is not None
        assert record.state == OrderState.FILLED
        assert record.payload["symbol"] == "BTC/USD"

    def test_multiple_orders_different_nonces(self):
        engine = IdempotentEngine()
        nonce1 = engine.generate_nonce()
        nonce2 = engine.generate_nonce()
        s1, _ = engine.submit(nonce1, {"order": 1})
        s2, _ = engine.submit(nonce2, {"order": 2})
        assert s1 == OrderState.PENDING
        assert s2 == OrderState.PENDING
        assert engine.cache_size() == 2


# === STATE UPDATES ===
class TestStateUpdates:
    def test_update_pending_to_filled(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        record = engine.update_state(nonce, OrderState.FILLED)
        assert record is not None
        assert record.state == OrderState.FILLED

    def test_update_unknown_nonce_returns_none(self):
        engine = IdempotentEngine()
        result = engine.update_state("nonexistent", OrderState.FILLED)
        assert result is None

    def test_get_after_update(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        engine.update_state(nonce, OrderState.CANCELLED)
        record = engine.get(nonce)
        assert record is not None
        assert record.state == OrderState.CANCELLED


# === GET & TTL EXPIRATION ===
class TestTTLOrder:
    def test_get_returns_record_before_ttl(self):
        engine = IdempotentEngine(ttl_s=10.0)
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        record = engine.get(nonce)
        assert record is not None
        assert record.payload["symbol"] == "BTC/USD"

    def test_get_returns_none_after_ttl(self):
        engine = IdempotentEngine(ttl_s=0.2)
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        time.sleep(0.3)
        record = engine.get(nonce)
        assert record is None

    def test_submit_expired_nonce_allows_resubmit(self):
        engine = IdempotentEngine(ttl_s=0.2)
        nonce = engine.generate_nonce()
        engine.submit(nonce, {"symbol": "BTC/USD"})
        time.sleep(0.3)
        # Original should be expired, so submit should create new
        state, record = engine.submit(nonce, {"symbol": "ETH/USD"})
        assert state == OrderState.PENDING
        assert record is None

    def test_evict_expired(self):
        engine = IdempotentEngine(ttl_s=0.2)
        n1 = engine.generate_nonce()
        n2 = engine.generate_nonce()
        engine.submit(n1, {"order": 1})
        engine.submit(n2, {"order": 2})
        time.sleep(0.3)
        count = engine.evict_expired()
        assert count == 2
        assert engine.cache_size() == 0

    def test_evict_expired_partial(self):
        engine = IdempotentEngine(ttl_s=0.2)
        n1 = engine.generate_nonce()
        n2 = engine.generate_nonce()
        engine.submit(n1, {"order": 1})
        time.sleep(0.3)
        engine.submit(n2, {"order": 2})
        count = engine.evict_expired()
        assert count == 1
        assert engine.cache_size() == 1


# === LRU EVICTION ===
class TestLRUEviction:
    def test_eviction_when_full(self):
        engine = IdempotentEngine(cache_maxsize=3, ttl_s=86400)
        nonces = [engine.generate_nonce() for _ in range(4)]
        for i, n in enumerate(nonces):
            engine.submit(n, {"order": i})
        assert engine.cache_size() == 3
        # Oldest (first) should be evicted
        assert engine.get(nonces[0]) is None
        assert engine.get(nonces[3]) is not None

    def test_eviction_keeps_recent(self):
        engine = IdempotentEngine(cache_maxsize=2, ttl_s=86400)
        n1 = engine.generate_nonce()
        n2 = engine.generate_nonce()
        n3 = engine.generate_nonce()
        for n in [n1, n2, n3]:
            engine.submit(n, {"order": 1})
        assert engine.get(n1) is None
        assert engine.get(n2) is not None
        assert engine.get(n3) is not None


# === CLEAR & EDGE CASES ===
class TestEdgeCases:
    def test_clear(self):
        engine = IdempotentEngine()
        for _ in range(5):
            nonce = engine.generate_nonce()
            engine.submit(nonce, {"test": 1})
        assert engine.cache_size() == 5
        engine.clear()
        assert engine.cache_size() == 0

    def test_invalid_maxsize(self):
        with pytest.raises(AssertionError):
            IdempotentEngine(cache_maxsize=0)

    def test_invalid_ttl(self):
        with pytest.raises(AssertionError):
            IdempotentEngine(ttl_s=0)

    def test_all_order_states(self):
        engine = IdempotentEngine()
        for state in OrderState:
            nonce = engine.generate_nonce()
            engine.submit(nonce, {"test": 1})
            engine.update_state(nonce, state)
            record = engine.get(nonce)
            assert record.state == state

    def test_payload_is_copy(self):
        engine = IdempotentEngine()
        nonce = engine.generate_nonce()
        payload = {"symbol": "BTC/USD"}
        engine.submit(nonce, payload)
        payload["symbol"] = "MODIFIED"
        record = engine.get(nonce)
        assert record.payload["symbol"] == "BTC/USD"
