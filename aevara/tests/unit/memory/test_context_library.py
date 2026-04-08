# @module: aevara.tests.unit.memory.test_context_library
# @deps: aevara.src.memory.context_library
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para ContextLibrary: happy path, edge cases, error cases,
#           e property-based com Hypothesis.

from __future__ import annotations

import time
import numpy as np
import pytest
from hypothesis import given, strategies as st

from aevara.src.memory.context_library import ContextLibrary, MemoryEntry


def make_entry(entry_id: str, dim: int = 64, decay: float = 0.1) -> MemoryEntry:
    rng = np.random.RandomState(hash(entry_id) % 2**31)
    return MemoryEntry(
        id=entry_id,
        embedding=rng.randn(dim).astype(np.float32),
        context_vector={"alpha": rng.rand()},
        outcome_score=float(rng.uniform(-0.5, 0.5)),
        timestamp_ns=time.time_ns(),
        decay_rate=decay,
        tags=("test",),
    )


# === HAPPY PATH ===
class TestContextLibraryHappyPath:
    def test_store_and_retrieve(self):
        lib = ContextLibrary(embedding_dim=64)
        entry = make_entry("test_001")
        lib.store(entry)
        assert lib.size == 1
        assert lib.get("test_001") is entry

    def test_store_overwrites(self):
        lib = ContextLibrary(embedding_dim=64)
        lib.store(make_entry("e1"))
        lib.store(make_entry("e1"))
        assert lib.size == 1

    def test_query_returns_results(self):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        entry = make_entry("e1", dim=dim)
        lib.store(entry)
        results = lib.query(entry.embedding, top_k=5)
        assert len(results) >= 1
        assert results[0][0] == "e1"

    def test_serialize_deserialize_identity(self):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        for i in range(5):
            lib.store(make_entry(f"e{i}", dim=dim))
        data = lib.serialize()
        lib2 = ContextLibrary.deserialize(data)
        assert lib2.embedding_dim == lib.embedding_dim
        assert lib2.size == lib.size
        for eid in lib.get_all_ids():
            assert lib2.get(eid) is not None


# === EDGE CASES ===
class TestContextLibraryEdgeCases:
    def test_empty_library_query_returns_empty(self):
        lib = ContextLibrary(embedding_dim=32)
        results = lib.query(np.zeros(32))
        assert results == []

    def test_zero_embedding_query_returns_empty(self):
        lib = ContextLibrary(embedding_dim=32)
        lib.store(make_entry("e1", dim=32))
        results = lib.query(np.zeros(32))
        assert results == []

    def test_min_similarity_filters_all(self):
        dim = 64
        lib = ContextLibrary(embedding_dim=dim)
        lib.store(make_entry("e1", dim=dim))
        query_vec = np.ones(dim) * -1  # Opposite direction
        results = lib.query(query_vec, top_k=5, min_similarity=0.9)
        assert len(results) == 0

    def test_top_k_limits_results(self):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        for i in range(10):
            lib.store(make_entry(f"e{i}", dim=dim))
        query_vec = np.random.randn(dim)
        results = lib.query(query_vec, top_k=3)
        assert len(results) <= 3

    def test_explicit_top_k_greater_than_entry_count(self):
        lib = ContextLibrary(embedding_dim=32)
        lib.store(make_entry("e1", dim=32))
        results = lib.query(np.random.randn(32), top_k=100)
        assert len(results) <= 1


# === ERROR CASES ===
class TestContextLibraryErrors:
    def test_embedding_dim_mismatch_store(self):
        lib = ContextLibrary(embedding_dim=64)
        entry = make_entry("bad", dim=32)
        with pytest.raises(AssertionError, match="dim mismatch"):
            lib.store(entry)

    def test_embedding_dim_mismatch_query(self):
        lib = ContextLibrary(embedding_dim=64)
        with pytest.raises(AssertionError, match="Query embedding dim mismatch"):
            lib.query(np.zeros(32))

    def test_invalid_max_capacity(self):
        with pytest.raises(AssertionError):
            ContextLibrary(embedding_dim=32, max_capacity=0)

    def test_invalid_embedding_dim(self):
        with pytest.raises(AssertionError):
            ContextLibrary(embedding_dim=0)

    def test_invalid_outcome_score(self):
        with pytest.raises(AssertionError, match="outcome_score"):
            MemoryEntry(
                id="bad", embedding=np.zeros(32), context_vector={},
                outcome_score=2.0, timestamp_ns=1, decay_rate=0.1,
            )

    def test_invalid_decay_rate_zero(self):
        with pytest.raises(AssertionError, match="decay_rate"):
            MemoryEntry(
                id="bad", embedding=np.zeros(32), context_vector={},
                outcome_score=0.0, timestamp_ns=1, decay_rate=0.0,
            )

    def test_invalid_embedding_2d(self):
        with pytest.raises(AssertionError, match="must be 1D"):
            MemoryEntry(
                id="bad", embedding=np.zeros((4, 8)), context_vector={},
                outcome_score=0.0, timestamp_ns=1, decay_rate=0.1,
            )


# === PROPERTY-BASED (HYPOTHESIS) ===
class TestContextLibraryProperties:
    @given(st.integers(min_value=1, max_value=20), st.integers(min_value=1, max_value=50))
    def test_query_never_exceeds_top_k(self, n_entries, top_k):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        for i in range(n_entries):
            lib.store(make_entry(f"e{i}", dim=dim))
        query_vec = np.random.randn(dim)
        results = lib.query(query_vec, top_k=top_k, min_similarity=0.0)
        assert len(results) <= top_k

    @given(st.integers(min_value=1, max_value=100))
    def test_serialization_roundtrip(self, n_entries):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        for i in range(n_entries):
            lib.store(make_entry(f"e{i}", dim=dim))
        data = lib.serialize()
        lib2 = ContextLibrary.deserialize(data)
        assert lib2.size == lib.size

    def test_access_count_increments_on_query(self):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim)
        entry = make_entry("e1", dim=dim)
        lib.store(entry)
        initial_count = lib.get("e1").access_count
        lib.query(entry.embedding, top_k=5)
        assert lib.get("e1").access_count >= initial_count

    def test_prune_reduces_to_target(self):
        dim = 32
        lib = ContextLibrary(embedding_dim=dim, max_capacity=10)
        for i in range(20):
            lib.store(make_entry(f"e{i}", dim=dim))
        assert lib.size == 20
        pruned = lib.prune_count(max_entries=15)
        assert lib.size == 20  # prune_count doesn't modify
        assert pruned == 5
