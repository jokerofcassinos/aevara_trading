from aevara.src.memory.checkpoint_serializer import CheckpointSerializer
import os

def test_atomic_persistence():
    test_path = "aevara/state/test_cp.json"
    state = {"test_key": "test_value", "nested": {"a": 1}}
    
    # 1. Save
    assert CheckpointSerializer.serialize_state(state, test_path) is True
    assert os.path.exists(test_path)
    
    # 2. Load
    loaded = CheckpointSerializer.deserialize_state(test_path)
    assert loaded == state
    
    # 3. Integrity Test
    with open(test_path, "r") as f:
        data = f.read()
    
    # Corrupt data
    corrupted_data = data.replace("test_value", "corrupted")
    with open(test_path, "w") as f:
        f.write(corrupted_data)
        
    loaded_corrupted = CheckpointSerializer.deserialize_state(test_path)
    assert loaded_corrupted is None # Should fail due to checksum mismatch
    
    if os.path.exists(test_path):
        os.remove(test_path)
    print("✅ CheckpointSerializer Atomic Persistence Test: PASS")

if __name__ == "__main__":
    test_atomic_persistence()
