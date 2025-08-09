"""Tests for RedactionState data structure."""

import json
from datetime import datetime

import pytest
from redactyl.types import PIIEntity, PIIType, RedactionState, RedactionToken


class TestRedactionState:
    """Test RedactionState data structure and serialization."""
    
    @pytest.fixture
    def sample_entity(self):
        """Create a sample PII entity."""
        return PIIEntity(
            type=PIIType.EMAIL,
            value="john@example.com",
            start=10,
            end=26,
            confidence=0.95
        )
    
    @pytest.fixture
    def sample_token(self, sample_entity):
        """Create a sample redaction token."""
        return RedactionToken(
            original="john@example.com",
            pii_type=PIIType.EMAIL,
            token_index=1,
            entity=sample_entity
        )
    
    def test_create_empty_state(self):
        """Test creating an empty redaction state."""
        state = RedactionState()
        
        assert state.tokens == {}
        assert state.metadata == {}
        assert isinstance(state.created_at, datetime)
    
    def test_create_state_with_tokens(self, sample_token):
        """Test creating state with initial tokens."""
        tokens = {sample_token.token: sample_token}
        metadata = {"source": "test"}
        
        state = RedactionState(
            tokens=tokens,
            metadata=metadata
        )
        
        assert state.tokens == tokens
        assert state.metadata == metadata
    
    def test_state_immutability(self, sample_token):
        """Test that RedactionState is immutable."""
        state = RedactionState(
            tokens={sample_token.token: sample_token}
        )
        
        # Test token dict immutability
        with pytest.raises(AttributeError):
            state.tokens = {}
        
        # Test metadata immutability
        with pytest.raises(AttributeError):
            state.metadata = {"new": "data"}
        
        # Test created_at immutability
        with pytest.raises(AttributeError):
            state.created_at = datetime.now()
    
    def test_redaction_token_generation(self, sample_entity):
        """Test RedactionToken token generation."""
        token = RedactionToken(
            original="test@example.com",
            pii_type=PIIType.EMAIL,
            token_index=3,
            entity=sample_entity
        )
        
        assert token.token == "[EMAIL_3]"
        
        name_token = RedactionToken(
            original="Jane",
            pii_type=PIIType.NAME_FIRST,
            token_index=1,
            entity=PIIEntity(
                type=PIIType.NAME_FIRST,
                value="Jane",
                start=0,
                end=4,
                confidence=0.9
            )
        )
        
        assert name_token.token == "[NAME_FIRST_1]"
    
    def test_serialization_to_dict(self, sample_token):
        """Test serializing state to dictionary."""
        state = RedactionState(
            tokens={sample_token.token: sample_token},
            metadata={"version": "1.0"}
        )
        
        data = state.to_dict()
        
        assert "[EMAIL_1]" in data["tokens"]
        assert data["tokens"]["[EMAIL_1]"]["original"] == "john@example.com"
        assert data["tokens"]["[EMAIL_1]"]["pii_type"] == "EMAIL"
        assert data["tokens"]["[EMAIL_1]"]["token_index"] == 1
        assert data["metadata"]["version"] == "1.0"
        assert "created_at" in data
    
    def test_deserialization_from_dict(self, sample_token):
        """Test deserializing state from dictionary."""
        original_state = RedactionState(
            tokens={sample_token.token: sample_token},
            metadata={"test": True}
        )
        
        data = original_state.to_dict()
        restored_state = RedactionState.from_dict(data)
        
        assert len(restored_state.tokens) == 1
        assert "[EMAIL_1]" in restored_state.tokens
        assert restored_state.tokens["[EMAIL_1]"].original == sample_token.original
        assert restored_state.metadata["test"] is True
        assert restored_state.created_at == original_state.created_at
    
    def test_json_serialization(self, sample_token):
        """Test JSON serialization and deserialization."""
        state = RedactionState(
            tokens={sample_token.token: sample_token},
            metadata={"json_test": "value"}
        )
        
        json_str = state.to_json()
        assert isinstance(json_str, str)
        
        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert "[EMAIL_1]" in parsed["tokens"]
        
        # Test round-trip
        restored = RedactionState.from_json(json_str)
        assert restored.tokens.keys() == state.tokens.keys()
        assert restored.metadata == state.metadata
    
    def test_with_token_immutable_update(self, sample_token):
        """Test immutable token addition."""
        state1 = RedactionState()
        
        # Add a token
        state2 = state1.with_token(sample_token.token, sample_token)
        
        # Original state unchanged
        assert len(state1.tokens) == 0
        assert len(state2.tokens) == 1
        assert sample_token.token in state2.tokens
        
        # Metadata and created_at preserved
        assert state2.metadata == state1.metadata
        assert state2.created_at == state1.created_at
    
    def test_merge_states(self):
        """Test merging two states."""
        entity1 = PIIEntity(
            type=PIIType.EMAIL,
            value="first@example.com",
            start=0,
            end=17,
            confidence=0.9
        )
        token1 = RedactionToken(
            original="first@example.com",
            pii_type=PIIType.EMAIL,
            token_index=1,
            entity=entity1
        )
        
        entity2 = PIIEntity(
            type=PIIType.PHONE,
            value="555-1234",
            start=20,
            end=28,
            confidence=0.95
        )
        token2 = RedactionToken(
            original="555-1234",
            pii_type=PIIType.PHONE,
            token_index=1,
            entity=entity2
        )
        
        state1 = RedactionState(
            tokens={token1.token: token1},
            metadata={"source": "email"}
        )
        
        state2 = RedactionState(
            tokens={token2.token: token2},
            metadata={"source": "phone", "extra": "data"}
        )
        
        merged = state1.merge(state2)
        
        # Both tokens present
        assert len(merged.tokens) == 2
        assert "[EMAIL_1]" in merged.tokens
        assert "[PHONE_1]" in merged.tokens
        
        # Metadata merged (state2 overwrites state1)
        assert merged.metadata["source"] == "phone"
        assert merged.metadata["extra"] == "data"
        
        # Earlier created_at preserved
        assert merged.created_at == min(state1.created_at, state2.created_at)
        
        # Original states unchanged
        assert len(state1.tokens) == 1
        assert len(state2.tokens) == 1
    
    def test_unredaction_issue(self):
        """Test UnredactionIssue creation and string representation."""
        from redactyl.types import UnredactionIssue
        
        # Hallucination issue
        issue1 = UnredactionIssue(
            token="[EMAIL_2]",
            issue_type="hallucination",
            replacement=None,
            confidence=0.0,
            details="Token not found in state"
        )
        
        assert str(issue1) == "hallucination: [EMAIL_2] (no replacement found)"
        
        # Fuzzy match issue
        issue2 = UnredactionIssue(
            token="[EMIAL_1]",  # Typo
            issue_type="fuzzy_match",
            replacement="john@example.com",
            confidence=0.85,
            details="Likely typo in token"
        )
        
        assert str(issue2) == "fuzzy_match: [EMIAL_1] → john@example.com (confidence: 0.85)"