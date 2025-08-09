"""Tests for core PIILoop functionality."""

import pytest
from redactyl import PIIEntity, PIIType, RedactionState, RedactionToken
from redactyl.core import PIILoop
from redactyl.detectors.mock import MockDetector


class TestCoreLoop:
    """Test the core round-trip functionality."""
    
    def test_simple_round_trip(self):
        """The fundamental promise: what goes out must come back"""
        detector = MockDetector([
            PIIEntity(
                type=PIIType.PERSON,
                value="John Doe",
                start=8,
                end=16,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="john@example.com",
                start=20,
                end=36,
                confidence=0.98
            )
        ])
        
        shield = PIILoop(detector=detector)
        original = "Contact John Doe at john@example.com"
        
        redacted, state = shield.redact(original)
        assert "John Doe" not in redacted
        assert "john@example.com" not in redacted
        assert "[PERSON_1]" in redacted
        assert "[EMAIL_1]" in redacted
        
        unredacted, issues = shield.unredact(redacted, state)
        assert unredacted == original
        assert len(issues) == 0
    
    def test_empty_text(self):
        """Test handling of empty text."""
        shield = PIILoop(detector=MockDetector([]))
        
        redacted, state = shield.redact("")
        assert redacted == ""
        assert len(state.tokens) == 0
        
        unredacted, issues = shield.unredact("", state)
        assert unredacted == ""
        assert len(issues) == 0
    
    def test_no_pii_detected(self):
        """Test text with no PII."""
        shield = PIILoop(detector=MockDetector([]))
        original = "This is just regular text with no PII"
        
        redacted, state = shield.redact(original)
        assert redacted == original
        assert len(state.tokens) == 0
        
        unredacted, issues = shield.unredact(original, state)
        assert unredacted == original
        assert len(issues) == 0
    
    def test_multiple_same_type_entities(self):
        """Test handling multiple entities of the same type."""
        detector = MockDetector([
            PIIEntity(
                type=PIIType.EMAIL,
                value="first@example.com",
                start=8,
                end=25,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="second@example.com",
                start=30,
                end=48,
                confidence=0.95
            )
        ])
        
        shield = PIILoop(detector=detector)
        original = "Contact first@example.com and second@example.com"
        
        redacted, state = shield.redact(original)
        assert "first@example.com" not in redacted
        assert "second@example.com" not in redacted
        assert "[EMAIL_1]" in redacted
        assert "[EMAIL_2]" in redacted
        
        # Verify correct ordering
        assert redacted == "Contact [EMAIL_1] and [EMAIL_2]"
        
        unredacted, issues = shield.unredact(redacted, state)
        assert unredacted == original
        assert len(issues) == 0
    
    def test_overlapping_entities_rejected(self):
        """Test that overlapping entities are handled properly."""
        detector = MockDetector([
            PIIEntity(
                type=PIIType.PERSON,
                value="John Doe Smith",
                start=0,
                end=14,
                confidence=0.9
            ),
            PIIEntity(
                type=PIIType.PERSON,
                value="Doe Smith",
                start=5,
                end=14,
                confidence=0.8
            )
        ])
        
        shield = PIILoop(detector=detector)
        original = "John Doe Smith is here"
        
        # Should keep only the higher confidence, non-overlapping entity
        redacted, state = shield.redact(original)
        assert redacted == "[PERSON_1] is here"
        assert len(state.tokens) == 1