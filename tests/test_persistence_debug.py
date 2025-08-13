"""Debug test for persistence."""

from redactyl.entity_tracker import GlobalEntityTracker
from redactyl.types import PIIEntity, PIIType


def test_entity_tracker_persistence():
    """Test that GlobalEntityTracker persists across calls."""
    tracker = GlobalEntityTracker()
    
    # First batch
    entities1 = {
        "field1": [PIIEntity(PIIType.EMAIL, "alice@example.com", 0, 17, 0.95)]
    }
    tokens1 = tracker.assign_tokens(entities1)
    print(f"Batch 1: {tokens1}")
    
    # Second batch with new email
    entities2 = {
        "field2": [PIIEntity(PIIType.EMAIL, "bob@example.com", 0, 15, 0.95)]
    }
    tokens2 = tracker.assign_tokens(entities2)
    print(f"Batch 2: {tokens2}")
    
    # Third batch with repeated email
    entities3 = {
        "field3": [PIIEntity(PIIType.EMAIL, "alice@example.com", 0, 17, 0.95)]
    }
    tokens3 = tracker.assign_tokens(entities3)
    print(f"Batch 3: {tokens3}")
    
    # Check tokens
    assert tokens1["field1"][0].token_index == 1
    assert tokens2["field2"][0].token_index == 2
    assert tokens3["field3"][0].token_index == 1  # Should reuse


if __name__ == "__main__":
    test_entity_tracker_persistence()