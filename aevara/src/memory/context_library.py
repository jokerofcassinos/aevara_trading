# @module: aevara.src.memory.context_library
# @deps: numpy
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Persistent contextual memory with semantic decay, query-by-similarity,
#           and bounded retention. Entries expire via exponential decay; pruned
#           entries are archived, not deleted. All contracts are immutable.

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """
    Entry in the context library. Frozen + slots = immutavel por construcao.
    Embedding dimension is fixed at creation time (must match library dim).
    """
    id: str
    embedding: np.ndarray                    # Fixed dimension (e.g., 32 or 64)
    context_vector: Dict[str, float]         # Named feature values
    outcome_score: float                     # [-1, 1] — success metric
    timestamp_ns: int                        # Creation time
    decay_rate: float                        # (0, 1] — learned or heuristic
    tags: Tuple[str, ...] = ()              # Categorization
    last_accessed_ns: int = 0                # Updated on access
    access_count: int = 0                    # LRU tracking

    def is_expired(self, current_ns: int, max_age_ns: int) -> bool:
        return (current_ns - self.timestamp_ns) > max_age_ns

    def decay_weight(self, current_ns: int) -> float:
        """Exponential decay: w = exp(-rate * dt_seconds)."""
        dt = (current_ns - self.timestamp_ns) / 1e9
        return np.exp(-self.decay_rate * dt)

    def __post_init__(self) -> None:
        assert -1.0 <= self.outcome_score <= 1.0, "outcome_score must be in [-1, 1]"
        assert 0.0 < self.decay_rate <= 1.0, "decay_rate must be in (0, 1]"
        assert len(self.embedding.shape) == 1, "embedding must be 1D"
        if self.last_accessed_ns == 0:
            object.__setattr__(self, "last_accessed_ns", self.timestamp_ns)


class ContextLibrary:
    """
    Persistent context store with semantic decay.

    Invariants:
    - len(entries) <= max_capacity (after prune)
    - All entries share same embedding dimension
    - Query returns <= top_k results
    - Deserialize after serialize is identity (idempotent)
    """

    def __init__(self, embedding_dim: int = 64, max_capacity: int = 10000,
                 default_max_age_ns: int = 86400 * 30 * 1_000_000_000):  # 30 days in ns
        assert embedding_dim > 0, "embedding_dim must be positive"
        assert max_capacity > 0, "max_capacity must be positive"
        self._embedding_dim = embedding_dim
        self._max_capacity = max_capacity
        self._default_max_age_ns = default_max_age_ns
        self._entries: Dict[str, MemoryEntry] = {}
        self._archive: Dict[str, MemoryEntry] = {}

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def archive_size(self) -> int:
        return len(self._archive)

    def store(self, entry: MemoryEntry) -> str:
        """
        Store entry, overwriting existing. Validates embedding dim.
        Returns entry.id.
        """
        assert entry.embedding.shape[0] == self._embedding_dim, (
            f"Embedding dim mismatch: expected {self._embedding_dim}, got {entry.embedding.shape[0]}"
        )
        self._entries[entry.id] = entry
        return entry.id

    def query(self, embedding: np.ndarray, top_k: int = 5,
              min_similarity: float = 0.3, current_ns: Optional[int] = None) -> List[Tuple[str, float]]:
        """
        Query by cosine similarity. Returns sorted list of (entry_id, weighted_similarity).

        Weighted similarity = cosine_sim * decay_weight.
        Only returns entries with weighted_similarity >= min_similarity.
        Always returns <= top_k results.

        Args:
            embedding: Query embedding (must match library dim)
            top_k: Maximum results
            min_similarity: Minimum weighted similarity threshold
            current_ns: Current time (default: now)

        Returns:
            List of (entry_id, weighted_score) sorted descending
        """
        assert embedding.shape[0] == self._embedding_dim, "Query embedding dim mismatch"

        now = current_ns or time.time_ns()
        query_norm = np.linalg.norm(embedding)
        if query_norm < 1e-12:
            return []

        results: List[Tuple[str, float]] = []
        for eid, entry in self._entries.items():
            if entry.is_expired(now, self._default_max_age_ns):
                continue

            entry_norm = np.linalg.norm(entry.embedding)
            if entry_norm < 1e-12:
                continue

            cosine_sim = float(np.dot(embedding, entry.embedding) / (query_norm * entry_norm))
            # Map from [-1,1] to [0,1] for similarity
            cosine_sim = (cosine_sim + 1.0) / 2.0

            decay_w = entry.decay_weight(now)
            weighted_sim = cosine_sim * decay_w

            # Update access stats (create new frozen instance)
            updated = MemoryEntry(
                id=entry.id,
                embedding=entry.embedding,
                context_vector=entry.context_vector,
                outcome_score=entry.outcome_score,
                timestamp_ns=entry.timestamp_ns,
                decay_rate=entry.decay_rate,
                tags=entry.tags,
                last_accessed_ns=now,
                access_count=entry.access_count + 1,
            )
            self._entries[eid] = updated

            if weighted_sim >= min_similarity:
                results.append((eid, weighted_sim))

        # Sort descending, take top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return self._entries.get(entry_id)

    def prune(self, max_entries: Optional[int] = None, strategy: str = "decay_then_lru",
              current_ns: Optional[int] = None) -> int:
        """
        Prune entries to max_entries (default: max_capacity).
        Strategy: "decay_then_lru" — prune expired first, then oldest LRU.
        Returns number of entries pruned and archived.
        """
        limit = max_entries if max_entries is not None else self._max_capacity
        if len(self._entries) <= limit:
            return 0

        now = current_ns or time.time_ns()

        # Strategy: decay_then_lru
        # Step 1: Remove expired entries
        expired = [eid for eid, e in self._entries.items() if e.is_expired(now, self._default_max_age_ns)]
        for eid in expired:
            self._archive[eid] = self._entries.pop(eid)

        # Step 2: If still over limit, remove by lowest decay weight, then by oldest access
        while len(self._entries) > limit:
            target = min(self._entries.keys(), key=lambda eid: (
                self._entries[eid].decay_weight(now),
                self._entries[eid].last_accessed_ns,
            ))
            self._archive[target] = self._entries.pop(target)

        return len(self._archive) - (len(self._archive) if len(self._entries) > 0 else 0) + len(expired)

    def prune_count(self, max_entries: int, current_ns: Optional[int] = None) -> int:
        """Returns the number of entries that would be pruned (count only)."""
        now = current_ns or time.time_ns()
        to_prune = max(0, len(self._entries) - max_entries)
        return to_prune

    def get_all_ids(self) -> Set[str]:
        return set(self._entries.keys())

    def get_entries_with_tags(self, tags: Set[str]) -> List[MemoryEntry]:
        """Return entries matching any of the given tags."""
        return [e for e in self._entries.values() if tags & set(e.tags)]

    def serialize(self) -> bytes:
        """Serialize to bytes (JSON + base64 for embeddings)."""
        data = {
            "embedding_dim": self._embedding_dim,
            "max_capacity": self._max_capacity,
            "default_max_age_ns": self._default_max_age_ns,
            "entries": {}
        }
        for eid, entry in self._entries.items():
            data["entries"][eid] = {
                "id": entry.id,
                "embedding": entry.embedding.tolist(),
                "context_vector": entry.context_vector,
                "outcome_score": entry.outcome_score,
                "timestamp_ns": entry.timestamp_ns,
                "decay_rate": entry.decay_rate,
                "tags": entry.tags,
                "last_accessed_ns": entry.last_accessed_ns,
                "access_count": entry.access_count,
            }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> "ContextLibrary":
        """Deserialize from bytes. Idempotent with serialize."""
        obj = json.loads(data)
        lib = cls(
            embedding_dim=obj["embedding_dim"],
            max_capacity=obj["max_capacity"],
            default_max_age_ns=obj["default_max_age_ns"],
        )
        for eid, ed in obj["entries"].items():
            entry = MemoryEntry(
                id=ed["id"],
                embedding=np.array(ed["embedding"]),
                context_vector=ed["context_vector"],
                outcome_score=ed["outcome_score"],
                timestamp_ns=ed["timestamp_ns"],
                decay_rate=ed["decay_rate"],
                tags=tuple(ed["tags"]),
                last_accessed_ns=ed["last_accessed_ns"],
                access_count=ed["access_count"],
            )
            lib._entries[eid] = entry
        return lib

    def save_to_file(self, path: str) -> None:
        """Save to file with directory creation."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.serialize())

    @classmethod
    def load_from_file(cls, path: str) -> "ContextLibrary":
        with open(path, "rb") as f:
            return cls.deserialize(f.read())

    def clear(self) -> None:
        self._entries.clear()
