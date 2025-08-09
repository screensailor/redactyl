"""Tests for state accumulation across multiple texts."""

import pytest
from redactyl import PIIEntity, PIILoop, PIIType, RedactionState
from redactyl.detectors.mock import MockDetector


class TestStateAccumulation:
    """Test handling of state across multiple redaction operations."""
    
    def test_consecutive_redactions_same_loop(self):
        """Test that consecutive redactions maintain separate states."""
        detector1 = MockDetector([
            PIIEntity(
                type=PIIType.EMAIL,
                value="first@example.com",
                start=5,
                end=22,
                confidence=0.95
            )
        ])
        
        detector2 = MockDetector([
            PIIEntity(
                type=PIIType.EMAIL,
                value="second@example.com",
                start=8,
                end=26,
                confidence=0.95
            )
        ])
        
        # Create loop and use different detectors to simulate different texts
        loop = PIILoop(detector=detector1)
        
        # First redaction
        text1 = "Send first@example.com the info"
        redacted1, state1 = loop.redact(text1)
        assert redacted1 == "Send [EMAIL_1] the info"
        
        # Change detector for second text
        loop._detector = detector2
        
        # Second redaction (should have independent state)
        text2 = "Forward second@example.com too"
        redacted2, state2 = loop.redact(text2)
        assert redacted2 == "Forward [EMAIL_1] too"
        
        # States should be independent
        assert len(state1.tokens) == 1
        assert len(state2.tokens) == 1
        assert "[EMAIL_1]" in state1.tokens
        assert "[EMAIL_1]" in state2.tokens
        assert state1.tokens["[EMAIL_1]"].original == "first@example.com"
        assert state2.tokens["[EMAIL_1]"].original == "second@example.com"
    
    def test_merge_states_for_session(self):
        """Test merging states for multi-turn conversations."""
        # Create two separate states
        entity1 = PIIEntity(
            type=PIIType.EMAIL,
            value="alice@example.com",
            start=0,
            end=17,
            confidence=0.95
        )
        
        entity2 = PIIEntity(
            type=PIIType.PHONE,
            value="555-1234",
            start=26,
            end=34,
            confidence=0.90
        )
        
        entity3 = PIIEntity(
            type=PIIType.EMAIL,
            value="bob@example.com",
            start=0,
            end=15,
            confidence=0.95
        )
        
        # First turn
        loop1 = PIILoop(detector=MockDetector([entity1, entity2]))
        text1 = "alice@example.com or call 555-1234"
        redacted1, state1 = loop1.redact(text1)
        
        # Second turn
        loop2 = PIILoop(detector=MockDetector([entity3]))
        text2 = "Also contact bob@example.com"
        redacted2, state2 = loop2.redact(text2)
        
        # Merge states
        merged_state = state1.merge(state2)
        
        # Verify merged state behavior
        # Note: When merging, tokens with same keys will overwrite
        # This is a limitation - for proper session management, 
        # we'd need PIISession that maintains unique token counters
        assert len(merged_state.tokens) == 2  # [EMAIL_1] from state2 overwrites state1's
        assert "[EMAIL_1]" in merged_state.tokens
        assert "[PHONE_1]" in merged_state.tokens
        
        # The EMAIL_1 token now maps to bob@example.com (from state2)
        assert merged_state.tokens["[EMAIL_1]"].original == "bob@example.com"
        assert merged_state.tokens["[PHONE_1]"].original == "555-1234"
        
        # Test unredaction with merged state
        # This demonstrates the limitation - [EMAIL_1] will map to bob, not alice
        combined_response = "Reply to [EMAIL_1] and [PHONE_1]"
        unredacted, issues = loop1.unredact(combined_response, merged_state)
        assert unredacted == "Reply to bob@example.com and 555-1234"
        assert len(issues) == 0
    
    def test_token_counter_persistence(self):
        """Test that token counters reset between redactions."""
        # First text with two emails
        detector1 = MockDetector([
            PIIEntity(
                type=PIIType.EMAIL,
                value="email1@example.com",
                start=0,
                end=18,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="email2@example.com",
                start=23,
                end=41,
                confidence=0.95
            )
        ])
        
        loop = PIILoop(detector=detector1)
        text1 = "email1@example.com and email2@example.com"
        redacted1, state1 = loop.redact(text1)
        assert "[EMAIL_1]" in redacted1
        assert "[EMAIL_2]" in redacted1
        
        # Second text should start counters fresh
        detector2 = MockDetector([
            PIIEntity(
                type=PIIType.EMAIL,
                value="email3@example.com",
                start=0,
                end=18,
                confidence=0.95
            )
        ])
        
        loop._detector = detector2
        text2 = "email3@example.com is new"
        redacted2, state2 = loop.redact(text2)
        
        # Should be [EMAIL_1] not [EMAIL_3]
        assert "[EMAIL_1]" in redacted2
        assert "[EMAIL_3]" not in redacted2
    
    def test_state_immutability_in_accumulation(self):
        """Test that states remain immutable during accumulation."""
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="Alice",
            start=0,
            end=5,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        _, original_state = loop.redact("Alice is here")
        
        # Get a reference to the tokens dict
        original_tokens_count = len(original_state.tokens)
        
        # Merge with another state
        another_entity = PIIEntity(
            type=PIIType.PERSON,
            value="Bob",
            start=0,
            end=3,
            confidence=0.95
        )
        
        loop2 = PIILoop(detector=MockDetector([another_entity]))
        _, another_state = loop2.redact("Bob is there")
        
        merged = original_state.merge(another_state)
        
        # Original state should be unchanged
        assert len(original_state.tokens) == original_tokens_count
        # Merged state has only 1 token because both use [PERSON_1]
        # The second overwrites the first - this is expected behavior
        assert len(merged.tokens) == 1
        assert merged.tokens["[PERSON_1]"].original == "Bob"