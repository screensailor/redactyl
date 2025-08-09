"""Integration tests for edge cases and error scenarios."""

import dataclasses
import pytest
from redactyl import PIIEntity, PIILoop, PIIType, PIISession, RedactionState
from redactyl.detectors.mock import MockDetector


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_overlapping_tokens_in_llm_response(self):
        """Test when LLM response has overlapping token references."""
        entities = [
            PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state = loop.redact("test@example.com")
        
        # LLM creates overlapping tokens
        llm_response = "[EMAIL_1]@[EMAIL_1].com"  # Malformed
        
        unredacted, issues = loop.unredact(llm_response, state)
        # Should handle gracefully
        assert unredacted == "test@example.com@test@example.com.com"
        assert len(issues) == 0
    
    def test_nested_tokens(self):
        """Test when tokens appear inside other tokens."""
        entities = [
            PIIEntity(PIIType.PERSON, "John", 0, 4, 0.95),
            PIIEntity(PIIType.EMAIL, "john@example.com", 5, 21, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state = loop.redact("John john@example.com")
        
        # LLM nests tokens (shouldn't happen but test robustness)
        llm_response = "[[PERSON_1]_[EMAIL_1]]"
        
        unredacted, issues = loop.unredact(llm_response, state)
        assert unredacted == "[John_john@example.com]"
    
    def test_special_characters_in_pii(self):
        """Test PII containing special regex characters."""
        entities = [
            PIIEntity(PIIType.EMAIL, "user+tag@example.com", 0, 20, 0.95),
            PIIEntity(PIIType.PERSON, "O'Brien", 25, 32, 0.90),
            PIIEntity(PIIType.CUSTOM, "data[0]", 37, 44, 0.85)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "user+tag@example.com and O'Brien has data[0]"
        redacted, state = loop.redact(original)
        
        # Should handle special chars properly
        assert "[EMAIL_1]" in redacted
        assert "[PERSON_1]" in redacted
        assert "[CUSTOM_1]" in redacted
        
        unredacted, issues = loop.unredact(redacted, state)
        assert unredacted == original
        assert len(issues) == 0
    
    def test_unicode_and_emoji_handling(self):
        """Test handling of unicode characters and emojis."""
        # Note: The detector would provide byte positions, not character positions
        # For this test, we'll simulate proper byte positions
        text = "Contact José 🎉 García at josé@café.com"
        
        # Find actual byte positions
        person_start = text.find("José 🎉 García")
        person_end = person_start + len("José 🎉 García")
        email_start = text.find("josé@café.com")
        email_end = email_start + len("josé@café.com")
        
        entities = [
            PIIEntity(PIIType.PERSON, "José 🎉 García", person_start, person_end, 0.95),
            PIIEntity(PIIType.EMAIL, "josé@café.com", email_start, email_end, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        redacted, state = loop.redact(text)
        
        assert "[PERSON_1]" in redacted
        assert "[EMAIL_1]" in redacted
        assert "José" not in redacted
        assert "josé@café.com" not in redacted
        
        unredacted, issues = loop.unredact(redacted, state)
        assert unredacted == text
        assert len(issues) == 0
    
    def test_very_long_pii_values(self):
        """Test handling of unusually long PII values."""
        # Very long email address
        long_email = "a" * 100 + "@" + "b" * 100 + ".com"
        entities = [
            PIIEntity(PIIType.EMAIL, long_email, 6, 6 + len(long_email), 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = f"Email {long_email} is valid"
        redacted, state = loop.redact(original)
        
        assert "[EMAIL_1]" in redacted
        assert long_email not in redacted
        
        unredacted, issues = loop.unredact(redacted, state)
        assert unredacted == original
    
    def test_empty_pii_values(self):
        """Test handling of empty or whitespace PII values."""
        # Note: Empty PII values would have start=end which is invalid
        # Test whitespace only
        entities = [
            PIIEntity(PIIType.CUSTOM, "   ", 5, 8, 0.90)  # Whitespace at position 5-8
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Text    more text"  # 3 spaces at position 5-8
        redacted, state = loop.redact(original)
        
        # Should handle whitespace values
        assert "[CUSTOM_1]" in redacted
        assert len(state.tokens) == 1
    
    def test_malformed_token_formats(self):
        """Test various malformed token formats from LLM."""
        entities = [
            PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state = loop.redact("test@example.com")
        
        # Test various malformed tokens
        malformed_cases = [
            "[EMAIL_1",      # Missing closing bracket
            "EMAIL_1]",      # Missing opening bracket
            "[EMAIL_1]]",    # Extra closing bracket
            "[[EMAIL_1]",    # Extra opening bracket
            "[EMAIL 1]",     # Space in token
            "[email_1]",     # Lowercase (handled by fuzzy)
            "[EMAIL-1]",     # Different separator
            "[ EMAIL_1 ]",   # Spaces inside brackets
        ]
        
        for malformed in malformed_cases:
            unredacted, issues = loop.unredact(malformed, state)
            # Should not leak PII with malformed tokens (except lowercase which works without fuzzy)
            # Note: [EMAIL_1]] will partially match [EMAIL_1], leaving "]" - this is expected behavior
            if malformed == "[EMAIL_1]]":
                assert unredacted == "test@example.com]"
            elif malformed == "[[EMAIL_1]":
                assert unredacted == "[test@example.com"
            elif malformed != "[email_1]":
                assert "test@example.com" not in unredacted, f"PII leaked with malformed token: {malformed}"
    
    def test_token_at_boundaries(self):
        """Test tokens at text boundaries."""
        entities = [
            PIIEntity(PIIType.EMAIL, "start@example.com", 0, 17, 0.95),
            PIIEntity(PIIType.EMAIL, "end@example.com", 18, 33, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "start@example.com end@example.com"
        redacted, state = loop.redact(original)
        
        assert redacted == "[EMAIL_1] [EMAIL_2]"
        
        # Test tokens at start/end of response
        llm_responses = [
            "[EMAIL_1]",  # Only token
            "[EMAIL_1] text",  # Token at start
            "text [EMAIL_2]",  # Token at end
            "[EMAIL_1][EMAIL_2]",  # Adjacent tokens
        ]
        
        for response in llm_responses:
            unredacted, issues = loop.unredact(response, state)
            assert "start@example.com" in unredacted or "[EMAIL_1]" not in response
            assert "end@example.com" in unredacted or "[EMAIL_2]" not in response
    
    def test_concurrent_state_modifications(self):
        """Test that state immutability prevents issues."""
        entities = [
            PIIEntity(PIIType.PERSON, "Alice", 0, 5, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state1 = loop.redact("Alice")
        
        # Frozen dataclasses prevent attribute reassignment
        with pytest.raises(dataclasses.FrozenInstanceError):
            state1.tokens = {}
        
        # But dict itself is mutable - test we handle this correctly
        original_token = state1.tokens["[PERSON_1]"]
        # Try to modify the dict (this works but shouldn't affect unredaction)
        # since we should be using the token objects, not mutating state
        
        # Original state should work fine
        unredacted, _ = loop.unredact("[PERSON_1]", state1)
        assert unredacted == "Alice"
    
    def test_pii_types_case_sensitivity(self):
        """Test that PII types handle case properly."""
        # Test various PII type formats
        entities = [
            PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state = loop.redact("test@example.com")
        
        # Token should be uppercase
        assert "[EMAIL_1]" in state.tokens
        assert "[email_1]" not in state.tokens
    
    def test_session_with_no_pii(self):
        """Test session handling when no PII is detected."""
        loop = PIILoop(detector=MockDetector([]))
        
        with PIISession(loop) as session:
            # Multiple turns with no PII
            for i in range(5):
                text = f"This is message {i} with no PII"
                redacted = session.redact(text)
                assert redacted == text
            
            # State should remain empty
            state = session.get_state()
            assert len(state.tokens) == 0
    
    def test_extremely_large_token_indices(self):
        """Test handling of large token indices."""
        # Create many entities of same type with proper positions
        entities = []
        text_parts = []
        current_pos = 0
        
        for i in range(100):
            person_text = f"Person{i}"
            if i > 0:
                text_parts.append(" ")
                current_pos += 1
            
            text_parts.append(person_text)
            entities.append(
                PIIEntity(PIIType.PERSON, person_text, current_pos, current_pos + len(person_text), 0.95)
            )
            current_pos += len(person_text)
        
        original = "".join(text_parts)
        loop = PIILoop(detector=MockDetector(entities))
        
        redacted, state = loop.redact(original)
        
        # Should have PERSON_1 through PERSON_100
        assert "[PERSON_100]" in redacted
        assert "[PERSON_50]" in redacted
        assert "[PERSON_1]" in redacted
        
        # Verify no Person text remains
        for i in range(100):
            assert f"Person{i}" not in redacted
        
        # Test with session continuing numbering
        with PIISession(loop, initial_state=state) as session:
            # Add one more person
            loop._detector = MockDetector([
                PIIEntity(PIIType.PERSON, "Person101", 0, 9, 0.95)
            ])
            
            redacted_new = session.redact("Person101")
            assert redacted_new == "[PERSON_101]"  # Continues from 100
    
    def test_state_metadata_preservation(self):
        """Test that custom metadata is preserved through operations."""
        loop = PIILoop(detector=MockDetector([]))
        
        # Create state with custom metadata
        custom_state = RedactionState(
            tokens={},
            metadata={
                "request_id": "12345",
                "user_id": "user_abc",
                "custom_field": {"nested": "value"}
            }
        )
        
        # Use in session
        with PIISession(loop, initial_state=custom_state) as session:
            # Add some PII
            loop._detector = MockDetector([
                PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.95)
            ])
            session.redact("test@example.com")
            
            # Get final state
            final_state = session.get_state()
            
            # Metadata should be preserved
            assert final_state.metadata["request_id"] == "12345"
            assert final_state.metadata["user_id"] == "user_abc"
            assert final_state.metadata["custom_field"]["nested"] == "value"
    
    def test_token_collision_different_types(self):
        """Test that different PII types maintain separate counters."""
        entities = [
            PIIEntity(PIIType.PERSON, "John", 0, 4, 0.95),
            PIIEntity(PIIType.EMAIL, "john@example.com", 5, 21, 0.95),
            PIIEntity(PIIType.PHONE, "555-1234", 22, 30, 0.95),
            PIIEntity(PIIType.PERSON, "Jane", 31, 35, 0.95),
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "John john@example.com 555-1234 Jane"
        redacted, state = loop.redact(original)
        
        # Should have separate numbering per type
        assert "[PERSON_1]" in redacted
        assert "[EMAIL_1]" in redacted
        assert "[PHONE_1]" in redacted
        assert "[PERSON_2]" in redacted
        
        # All should unredact properly
        unredacted, issues = loop.unredact(redacted, state)
        assert unredacted == original
        assert len(issues) == 0