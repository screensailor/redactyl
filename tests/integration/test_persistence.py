"""Tests for state serialization and persistence."""

import json
from datetime import datetime
from pathlib import Path
import tempfile

import pytest
from redactyl import PIIEntity, PIILoop, PIIType, RedactionState, RedactionToken
from redactyl.detectors.mock import MockDetector


class TestPersistence:
    """Test state serialization and deserialization."""
    
    def test_json_round_trip(self):
        """Test JSON serialization and deserialization."""
        # Create a state with various tokens
        entities = [
            PIIEntity(
                type=PIIType.EMAIL,
                value="test@example.com",
                start=5,
                end=21,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.PERSON,
                value="John Doe",
                start=25,
                end=33,
                confidence=0.90
            ),
            PIIEntity(
                type=PIIType.PHONE,
                value="555-1234",
                start=40,
                end=48,
                confidence=0.85
            )
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original_text = "Send test@example.com to John Doe phone 555-1234"
        redacted, state = loop.redact(original_text)
        
        # Serialize to JSON
        json_str = state.to_json()
        
        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert "tokens" in parsed
        assert "metadata" in parsed
        assert "created_at" in parsed
        
        # Deserialize
        restored_state = RedactionState.from_json(json_str)
        
        # Verify state is preserved
        assert len(restored_state.tokens) == len(state.tokens)
        assert set(restored_state.tokens.keys()) == set(state.tokens.keys())
        
        # Verify we can use the restored state
        unredacted, issues = loop.unredact(redacted, restored_state)
        assert unredacted == original_text
        assert len(issues) == 0
    
    def test_file_persistence(self):
        """Test saving and loading from file."""
        # Create state
        entity = PIIEntity(
            type=PIIType.SSN,
            value="123-45-6789",
            start=4,
            end=15,
            confidence=0.99
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        _, state = loop.redact("SSN 123-45-6789")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(state.to_json())
            temp_path = Path(f.name)
        
        try:
            # Load from file
            with open(temp_path, 'r') as f:
                loaded_json = f.read()
            
            restored_state = RedactionState.from_json(loaded_json)
            
            # Verify restoration
            assert "[SSN_1]" in restored_state.tokens
            assert restored_state.tokens["[SSN_1]"].original == "123-45-6789"
        finally:
            # Clean up
            temp_path.unlink()
    
    def test_metadata_preservation(self):
        """Test that metadata is preserved through serialization."""
        # Create state with custom metadata
        state = RedactionState(
            tokens={},
            metadata={
                "session_id": "abc123",
                "user": "test_user",
                "config": {
                    "strict_mode": True,
                    "language": "en"
                }
            }
        )
        
        # Round trip through JSON
        json_str = state.to_json()
        restored = RedactionState.from_json(json_str)
        
        # Verify metadata preserved
        assert restored.metadata == state.metadata
        assert restored.metadata["session_id"] == "abc123"
        assert restored.metadata["config"]["strict_mode"] is True
    
    def test_timestamp_preservation(self):
        """Test that timestamps are preserved correctly."""
        # Create state with specific timestamp
        original_time = datetime(2024, 1, 15, 10, 30, 45, 123456)
        state = RedactionState(
            tokens={},
            metadata={},
            created_at=original_time
        )
        
        # Round trip
        json_str = state.to_json()
        restored = RedactionState.from_json(json_str)
        
        # Verify timestamp preserved (might lose microseconds in ISO format)
        assert restored.created_at.year == original_time.year
        assert restored.created_at.month == original_time.month
        assert restored.created_at.day == original_time.day
        assert restored.created_at.hour == original_time.hour
        assert restored.created_at.minute == original_time.minute
        assert restored.created_at.second == original_time.second
    
    def test_complex_token_preservation(self):
        """Test preservation of all token fields."""
        # Create tokens with all fields
        entity1 = PIIEntity(
            type=PIIType.NAME_FIRST,
            value="Jane",
            start=0,
            end=4,
            confidence=0.92
        )
        token1 = RedactionToken(
            original="Jane",
            pii_type=PIIType.NAME_FIRST,
            token_index=1,
            entity=entity1
        )
        
        entity2 = PIIEntity(
            type=PIIType.NAME_LAST,
            value="Doe",
            start=5,
            end=8,
            confidence=0.89
        )
        token2 = RedactionToken(
            original="Doe",
            pii_type=PIIType.NAME_LAST,
            token_index=1,
            entity=entity2
        )
        
        state = RedactionState(
            tokens={
                token1.token: token1,
                token2.token: token2
            }
        )
        
        # Round trip
        json_str = state.to_json()
        restored = RedactionState.from_json(json_str)
        
        # Verify all fields preserved
        for token_key in state.tokens:
            original_token = state.tokens[token_key]
            restored_token = restored.tokens[token_key]
            
            assert restored_token.original == original_token.original
            assert restored_token.pii_type == original_token.pii_type
            assert restored_token.token_index == original_token.token_index
            assert restored_token.entity.value == original_token.entity.value
            assert restored_token.entity.start == original_token.entity.start
            assert restored_token.entity.end == original_token.entity.end
            assert restored_token.entity.confidence == original_token.entity.confidence
    
    def test_empty_state_serialization(self):
        """Test serialization of empty state."""
        empty_state = RedactionState()
        
        json_str = empty_state.to_json()
        restored = RedactionState.from_json(json_str)
        
        assert len(restored.tokens) == 0
        assert len(restored.metadata) == 0
        assert isinstance(restored.created_at, datetime)