"""Tests for fuzzy matching in unredaction."""

import pytest
from redactyl import PIIEntity, PIILoop, PIIType
from redactyl.detectors.mock import MockDetector


class TestFuzzyMode:
    """Test fuzzy matching behavior."""
    
    def test_fuzzy_mode_enables_matching(self):
        """Test that fuzzy mode enables fuzzy matching."""
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        _, state = loop.redact("test@example.com")
        
        # LLM response with typo
        llm_response = "Contact [EMIAL_1] for details"
        
        # Default mode: no fuzzy matching
        unredacted_default, issues_default = loop.unredact(llm_response, state)
        assert "test@example.com" not in unredacted_default
        assert "[EMIAL_1]" in unredacted_default  # Token preserved
        assert len(issues_default) == 1
        assert issues_default[0].issue_type == "hallucination"
        
        # Fuzzy mode: enables fuzzy matching
        unredacted_fuzzy, issues_fuzzy = loop.unredact(llm_response, state, fuzzy=True)
        assert "test@example.com" in unredacted_fuzzy
        assert "[EMIAL_1]" not in unredacted_fuzzy
        assert len(issues_fuzzy) == 1
        assert issues_fuzzy[0].issue_type == "fuzzy_match"
    
    def test_fuzzy_mode_case_sensitivity(self):
        """Test that fuzzy mode handles case variations."""
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="Alice",
            start=0,
            end=5,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        _, state = loop.redact("Alice")
        
        # Case variation
        llm_response = "[person_1] is here"
        
        # Default mode: rejects case variations
        unredacted_default, issues_default = loop.unredact(llm_response, state)
        assert "Alice" not in unredacted_default
        assert "[person_1]" in unredacted_default
        assert len(issues_default) == 1
        assert issues_default[0].issue_type == "hallucination"
        
        # Fuzzy mode: matches case-insensitively
        unredacted_fuzzy, issues_fuzzy = loop.unredact(llm_response, state, fuzzy=True)
        assert "Alice" in unredacted_fuzzy
        assert len(issues_fuzzy) == 1
        assert issues_fuzzy[0].issue_type == "fuzzy_match"
    
    def test_exact_matches_work_in_both_modes(self):
        """Test that exact matches work in both modes."""
        entities = [
            PIIEntity(
                type=PIIType.EMAIL,
                value="alice@example.com",
                start=0,
                end=17,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.PHONE,
                value="555-1234",
                start=22,
                end=30,
                confidence=0.90
            )
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        _, state = loop.redact("alice@example.com and 555-1234")
        
        # Exact tokens
        response = "Contact [EMAIL_1] or call [PHONE_1]"
        
        # Both modes should handle exact matches
        unredacted_default, issues_default = loop.unredact(response, state)
        unredacted_fuzzy, issues_fuzzy = loop.unredact(response, state, fuzzy=True)
        
        assert unredacted_default == unredacted_fuzzy
        assert "alice@example.com" in unredacted_default
        assert "555-1234" in unredacted_default
        assert len(issues_default) == 0
        assert len(issues_fuzzy) == 0
    
    def test_fuzzy_mode_with_session(self):
        """Test fuzzy mode in PIISession."""
        from redactyl import PIISession
        
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="Bob",
            start=0,
            end=3,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        
        with PIISession(loop) as session:
            session.redact("Bob")
            
            # Typo in response
            response = "[PRESON_1] is ready"
            
            # Default (no fuzzy)
            unredacted_default, issues_default = session.unredact(response)
            assert "Bob" not in unredacted_default
            assert "[PRESON_1]" in unredacted_default
            
            # Fuzzy mode
            unredacted_fuzzy, issues_fuzzy = session.unredact(response, fuzzy=True)
            assert "Bob" in unredacted_fuzzy
    
    def test_default_mode_multiple_hallucinations(self):
        """Test default mode with multiple hallucinated tokens."""
        loop = PIILoop(detector=MockDetector([]))
        _, state = loop.redact("No PII")
        
        # Multiple hallucinated tokens with some that could fuzzy match
        response = "[PERSON_1], [EMAIL_1], [EMIAL_2], [PHONE_1]"
        
        # Default mode: all are hallucinations
        unredacted_default, issues_default = loop.unredact(response, state)
        assert all(issue.issue_type == "hallucination" for issue in issues_default)
        assert len(issues_default) == 4
        assert unredacted_default == response  # All tokens preserved
        
        # Fuzzy mode: might try fuzzy matching but still all hallucinations
        # because there's nothing in state to match against
        unredacted_fuzzy, issues_fuzzy = loop.unredact(response, state, fuzzy=True)
        assert all(issue.issue_type == "hallucination" for issue in issues_fuzzy)
        assert len(issues_fuzzy) == 4