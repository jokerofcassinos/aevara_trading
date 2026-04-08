# @module: aevara.tests.unit.memory.test_kg_persistence
# @deps: aevara.src.memory.knowledge_graph
# @status: TEST_PILOT
# @summary: Validation of atomic persistence cycle for KnowledgeGraph (T-030.2.1).

import os
import pytest
from aevara.src.memory.knowledge_graph import KnowledgeGraph

def test_kg_atomic_persistence():
    test_path = "aevara/state/test_kg.json"
    if os.path.exists(test_path): os.remove(test_path)
    
    kg = KnowledgeGraph()
    kg.add_node("n1", metadata={"key": "val"}, node_type="module")
    kg.add_node("n2", metadata={"type": "agent"})
    kg.add_edge("n1", "n2", "controls")
    
    # Save cycle
    kg.save(test_path)
    assert os.path.exists(test_path)
    
    # Load cycle
    kg2 = KnowledgeGraph()
    kg2.load(test_path)
    
    assert kg2.node_count == 2
    assert kg2.edge_count == 1
    assert kg2.get_node("n1").metadata["key"] == "val"
    assert kg2.get_neighbors("n1") == ["n2"]
    
    # Cleanup
    if os.path.exists(test_path): os.remove(test_path)

def test_kg_auto_create_dir():
    test_path = "aevara/state/temp_subdir/kg.json"
    kg = KnowledgeGraph()
    kg.add_node("x")
    kg.save(test_path)
    assert os.path.exists(test_path)
    
    import shutil
    shutil.rmtree("aevara/state/temp_subdir")
