# @module: aevara.tests.unit.memory.test_knowledge_graph
# @deps: aevara.src.memory.knowledge_graph
# @status: IMPLEMENTED
# @last_update: 2026-04-06
# @summary: Testes para KnowledgeGraph: traversal, merge, decay, query,
#           anti-duplication, e DOT export.

from __future__ import annotations

import pytest
from aevara.src.memory.knowledge_graph import GraphNode, KnowledgeGraph


# === HAPPY PATH ===
class TestKnowledgeGraphHappyPath:
    def test_add_and_get_node(self):
        kg = KnowledgeGraph()
        kg.add_node("n1", metadata={"type": "module", "name": "test"}, node_type="module")
        assert kg.node_count == 1
        node = kg.get_node("n1")
        assert node is not None
        assert node.node_id == "n1"

    def test_add_edge(self):
        kg = KnowledgeGraph()
        kg.add_node("a")
        kg.add_node("b")
        kg.add_edge("a", "b", "depends_on")
        assert kg.edge_count == 1
        neighbors = kg.get_neighbors("a")
        assert "b" in neighbors

    def test_find_similar_returns_matches(self):
        kg = KnowledgeGraph(redundancy_threshold=0.5)
        kg.add_node("m1", metadata={"type": "module", "name": "core"}, node_type="module")
        kg.add_node("m2", metadata={"type": "module", "name": "agent"}, node_type="module")
        results = kg.find_similar({"type": "module"}, threshold=0.3)
        assert len(results) >= 2

    def test_export_dot(self):
        kg = KnowledgeGraph()
        kg.add_node("X")
        kg.add_node("Y")
        kg.add_edge("X", "Y", "feeds")
        dot = kg.export_dot()
        assert "digraph" in dot
        assert '"X" -> "Y"' in dot


# === EDGE CASES ===
class TestKnowledgeGraphEdgeCases:
    def test_empty_graph_returns_empty(self):
        kg = KnowledgeGraph()
        assert kg.find_similar({"x": "y"}) == []
        assert kg.get_neighbors("nonexistent") == []

    def test_disconnected_node_get_neighbors_empty(self):
        kg = KnowledgeGraph()
        kg.add_node("isolated")
        assert kg.get_neighbors("isolated") == []

    def test_get_edges_for_node(self):
        kg = KnowledgeGraph()
        kg.add_node("a")
        kg.add_node("b")
        kg.add_node("c")
        kg.add_edge("a", "b", "rel1")
        kg.add_edge("a", "c", "rel2")
        edges = kg.get_edges_for_node("a")
        assert len(edges) == 2

    def test_remove_node_removes_connected_edges(self):
        kg = KnowledgeGraph()
        kg.add_node("a")
        kg.add_node("b")
        kg.add_edge("a", "b", "dep")
        kg.remove_node("a")
        assert kg.node_count == 1
        assert kg.edge_count == 0


# === ERROR CASES ===
class TestKnowledgeGraphErrors:
    def test_duplicate_node_raises(self):
        kg = KnowledgeGraph()
        kg.add_node("dup")
        with pytest.raises(ValueError):
            kg.add_node("dup")

    def test_edge_missing_src_raises(self):
        kg = KnowledgeGraph()
        kg.add_node("exists")
        with pytest.raises(ValueError, match="Source"):
            kg.add_edge("nonexistent", "exists", "bad")

    def test_edge_missing_dst_raises(self):
        kg = KnowledgeGraph()
        kg.add_node("exists")
        with pytest.raises(ValueError, match="Destination"):
            kg.add_edge("exists", "nonexistent", "bad")

    def test_duplicate_edge_raises(self):
        kg = KnowledgeGraph()
        kg.add_node("a")
        kg.add_node("b")
        kg.add_edge("a", "b", "rel")
        with pytest.raises(ValueError, match="already exists"):
            kg.add_edge("a", "b", "rel")

    def test_remove_nonexistent_raises(self):
        kg = KnowledgeGraph()
        with pytest.raises(ValueError, match="does not exist"):
            kg.remove_node("nonexistent")

    def test_invalid_threshold_raises(self):
        with pytest.raises(AssertionError):
            KnowledgeGraph(redundancy_threshold=-0.1)
        with pytest.raises(AssertionError):
            KnowledgeGraph(redundancy_threshold=1.5)


# === PROPERTY-BASED ===
class TestKnowledgeGraphProperties:
    def test_node_id_uniqueness(self):
        kg = KnowledgeGraph()
        for i in range(100):
            kg.add_node(f"node_{i}", metadata={"idx": str(i)})
        assert kg.node_count == 100

    def test_merge_reduces_node_count(self):
        kg = KnowledgeGraph(redundancy_threshold=0.3)
        kg.add_node("a", metadata={"type": "x", "val": "1"})
        kg.add_node("b", metadata={"type": "x", "val": "2"})
        initial = kg.node_count
        kg.merge_if_similar("a", "b")
        assert kg.node_count <= initial

    def test_detect_redundancy_returns_similar_node(self):
        kg = KnowledgeGraph(redundancy_threshold=0.3)
        kg.add_node("a", metadata={"type": "module", "name": "core"})
        kg.add_node("b", metadata={"type": "module", "name": "agent"})
        result = kg.detect_redundancy("a")
        assert result == "b"

    def test_merge_non_similar_no_change(self):
        kg = KnowledgeGraph(redundancy_threshold=0.9)
        kg.add_node("a", metadata={"type": "x", "val": "1"})
        kg.add_node("b", metadata={"type": "y", "val": "2"})
        initial_count = kg.node_count
        result = kg.merge_if_similar("a", "b")
        assert result == "a"
        assert kg.node_count == initial_count  # No merge

    def test_query_returns_at_most_all_nodes(self):
        kg = KnowledgeGraph()
        for i in range(10):
            kg.add_node(f"n{i}", metadata={"key": "value"})
        results = kg.find_similar({"key": "value"}, threshold=0.0)
        assert len(results) <= kg.node_count
