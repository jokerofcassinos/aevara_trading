# @module: aevara.src.memory.knowledge_graph
# @deps: json, os, dataclasses, typing
# @status: IMPLEMENTED_v1.1
# @last_update: 2026-04-10
# @summary: Knowledge Graph with Atomic JSON Persistence. Tracks relationships, similarity, and anti-duplication (Ψ-0).

from __future__ import annotations
import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    metadata: Dict[str, str]
    node_type: str = "generic"

    def similarity(self, other: "GraphNode") -> float:
        self_items = set(f"{k}={v}" for k, v in self.metadata.items())
        other_items = set(f"{k}={v}" for k, v in other.metadata.items())
        if not self_items and not other_items: return 0.0
        intersection = self_items & other_items
        union = self_items | other_items
        return len(intersection) / len(union) if union else 0.0

@dataclass(frozen=True, slots=True)
class GraphEdge:
    src: str
    dst: str
    relation: str
    weight: float = 1.0

class KnowledgeGraph:
    """
    AEVRA Knowledge Graph (v1.1.0).
    Implementa persistência atômica anti-corrupção e versionamento de schema.
    """
    VERSION = "1.0.0"

    def __init__(self, redundancy_threshold: float = 0.7):
        self._threshold = redundancy_threshold
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: Dict[Tuple[str, str, str], GraphEdge] = {}
        self._adj: Dict[str, List[str]] = {}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> List[str]:
        return list(self._adj.get(node_id, []))

    def find_similar(self, query_metadata: Dict[str, str], threshold: Optional[float] = None) -> List[str]:
        thr = threshold if threshold is not None else self._threshold
        # Note: metadata similarity logic is the same
        results = []
        for nid, node in self._nodes.items():
            # Minimal similarity logic for the patch
            self_items = set(f"{k}={v}" for k, v in query_metadata.items())
            other_items = set(f"{k}={v}" for k, v in node.metadata.items())
            if not self_items and not other_items: sim = 1.0
            else:
                intersection = self_items & other_items
                union = self_items | other_items
                sim = len(intersection) / len(union) if union else 0.0
            if sim >= thr: results.append((nid, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return [nid for nid, _ in results]

    def detect_redundancy(self, node_id: str) -> Optional[str]:
        if node_id not in self._nodes: return None
        node = self._nodes[node_id]
        for nid, other in self._nodes.items():
            if nid == node_id: continue
            if node.similarity(other) >= self._threshold: return nid
        return None

    def merge_if_similar(self, node_a: str, node_b: str) -> str:
        if node_a not in self._nodes or node_b not in self._nodes: return node_a
        a, b = self._nodes[node_a], self._nodes[node_b]
        if a.similarity(b) < self._threshold: return node_a
        # Simple merge: a absorbs b
        merged_metadata = {**a.metadata, **b.metadata}
        self._nodes[node_a] = GraphNode(node_a, merged_metadata, a.node_type)
        # Re-map edges from b to a
        edges_to_rem = []
        edges_to_add = []
        for k, e in self._edges.items():
            if e.src == node_b or e.dst == node_b:
                edges_to_rem.append(k)
                new_src = node_a if e.src == node_b else e.src
                new_dst = node_a if e.dst == node_b else e.dst
                if new_src != new_dst:
                    edges_to_add.append(GraphEdge(new_src, new_dst, e.relation, e.weight))
        for k in edges_to_rem: del self._edges[k]
        for e in edges_to_add: self.add_edge(e.src, e.dst, e.relation, e.weight)
        del self._nodes[node_b]
        if node_b in self._adj: del self._adj[node_b]
        return node_a

    def add_node(self, node_id: str, metadata: Optional[Dict[str, str]] = None, node_type: str = "generic"):
        if node_id in self._nodes: return
        self._nodes[node_id] = GraphNode(node_id=node_id, metadata=metadata or {}, node_type=node_type)
        if node_id not in self._adj: self._adj[node_id] = []

    def add_edge(self, src: str, dst: str, relation: str, weight: float = 1.0):
        if src not in self._nodes or dst not in self._nodes: return
        edge_key = (src, dst, relation)
        self._edges[edge_key] = GraphEdge(src, dst, relation, weight)
        if dst not in self._adj[src]: self._adj[src].append(dst)

    def save(self, path: str = "aevara/state/kg.json"):
        """Salva o grafo em JSON de forma atômica (temp + rename)."""
        data = {
            "version": self.VERSION,
            "nodes": [asdict(n) for n in self._nodes.values()],
            "edges": [{"src": e.src, "dst": e.dst, "rel": e.relation, "w": e.weight} for e in self._edges.values()]
        }
        
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Escrita Atômica
        fd, temp_path = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, path)
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            raise e

    def load(self, path: str = "aevara/state/kg.json"):
        """Carrega o grafo do disco se existir."""
        if not os.path.exists(path): return
        
        with open(path, 'r') as f:
            data = json.load(f)
            
        self.clear()
        for n in data.get("nodes", []):
            self.add_node(n["node_id"], n["metadata"], n["node_type"])
        for e in data.get("edges", []):
            self.add_edge(e["src"], e["dst"], e["rel"], e["w"])

    def clear(self):
        self._nodes.clear()
        self._edges.clear()
        self._adj.clear()
    
    def export_dot(self) -> str:
        lines = ["digraph KnowledgeGraph {", "  rankdir=LR;"]
        for nid, node in self._nodes.items():
            label = f"{nid}\\n[{node.node_type}]"
            lines.append(f'  "{nid}" [label="{label}"];')
        for (s, d, r), edge in self._edges.items():
            label = f"{r} ({edge.weight:.1f})"
            lines.append(f'  "{s}" -> "{d}" [label="{label}"];')
        lines.append("}")
        return "\n".join(lines)
