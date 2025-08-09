"""Test name component index grouping implementation."""

import pytest

from redactyl import PIILoop
from redactyl.detectors.mock import MockDetector
from redactyl.types import PIIEntity, PIIType


class TestNameComponentGrouping:
    """Test that name components from the same person get consistent indices."""

    def test_components_share_index(self) -> None:
        """Name components from same person should share the same index."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="John",
                    start=0,
                    end=4,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Smith",
                    start=5,
                    end=10,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "John Smith is here"
        redacted, state = loop.redact(text)
        
        # Both components should have index 1
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens
        assert redacted == "[NAME_FIRST_1] [NAME_LAST_1] is here"

    def test_same_first_name_reuses_index(self) -> None:
        """Same first name appearing later should reuse the person's index."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Jane",
                    start=13,
                    end=17,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Doe",
                    start=18,
                    end=21,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Jane",
                    start=44,
                    end=48,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "Meeting with Jane Doe tomorrow. Please remind Jane about it."
        redacted, state = loop.redact(text)
        
        # Both "Jane" instances should be [NAME_FIRST_1]
        assert state.tokens["[NAME_FIRST_1]"].original == "Jane"
        assert state.tokens["[NAME_LAST_1]"].original == "Doe"
        # Should only have these two tokens for names
        name_tokens = [t for t in state.tokens if "NAME_" in t]
        assert len(name_tokens) == 2

    def test_different_last_name_different_person(self) -> None:
        """Same first name with different last name is a different person."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="John",
                    start=0,
                    end=4,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Smith",
                    start=5,
                    end=10,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="John",
                    start=15,
                    end=19,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Doe",
                    start=20,
                    end=23,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "John Smith and John Doe are different"
        redacted, state = loop.redact(text)
        
        # Should have two different person indices
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens
        assert "[NAME_FIRST_2]" in state.tokens
        assert "[NAME_LAST_2]" in state.tokens
        
        # Verify the mapping
        assert state.tokens["[NAME_FIRST_1]"].original == "John"
        assert state.tokens["[NAME_LAST_1]"].original == "Smith"
        assert state.tokens["[NAME_FIRST_2]"].original == "John"
        assert state.tokens["[NAME_LAST_2]"].original == "Doe"

    def test_complex_name_components_grouped(self) -> None:
        """Complex names with title and middle names should group correctly."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_TITLE,
                    value="Dr",
                    start=0,
                    end=2,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Jane",
                    start=4,
                    end=8,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_MIDDLE,
                    value="Elizabeth",
                    start=9,
                    end=18,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Smith",
                    start=19,
                    end=24,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "Dr. Jane Elizabeth Smith is here"
        redacted, state = loop.redact(text)
        
        # All components should share index 1
        assert "[NAME_TITLE_1]" in state.tokens
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_MIDDLE_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens

    def test_partial_then_full_name(self) -> None:
        """First name only followed by full name should reuse the same person index."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Sarah",
                    start=11,
                    end=16,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Sarah",
                    start=51,
                    end=56,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Johnson",
                    start=57,
                    end=64,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "Please ask Sarah about the project. Best regards, Sarah Johnson"
        redacted, state = loop.redact(text)
        
        # Both Sarahs should be person 1 (order independence)
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens
        assert state.tokens["[NAME_FIRST_1]"].original == "Sarah"
        assert state.tokens["[NAME_LAST_1]"].original == "Johnson"
        # Should only have these two tokens for names
        name_tokens = [t for t in state.tokens if "NAME_" in t]
        assert len(name_tokens) == 2

    def test_multiple_people_mixed_patterns(self) -> None:
        """Multiple people with different naming patterns."""
        detector = MockDetector(
            entities=[
                # First person: Sarah (first name only)
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Sarah",
                    start=0,
                    end=5,
                    confidence=0.9,
                ),
                # Second person: John Smith (full name)
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="John",
                    start=17,
                    end=21,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Smith",
                    start=22,
                    end=27,
                    confidence=0.9,
                ),
                # Third person: Mary Elizabeth Johnson (full complex name)
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="Mary",
                    start=32,
                    end=36,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_MIDDLE,
                    value="Elizabeth",
                    start=37,
                    end=46,
                    confidence=0.9,
                ),
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Johnson",
                    start=47,
                    end=54,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "Sarah works with John Smith and Mary Elizabeth Johnson"
        redacted, state = loop.redact(text)
        
        # Verify three different people
        assert "[NAME_FIRST_1]" in state.tokens  # Sarah
        assert "[NAME_FIRST_2]" in state.tokens  # John
        assert "[NAME_LAST_2]" in state.tokens  # Smith
        assert "[NAME_FIRST_3]" in state.tokens  # Mary
        assert "[NAME_MIDDLE_3]" in state.tokens  # Elizabeth
        assert "[NAME_LAST_3]" in state.tokens  # Johnson

    def test_non_adjacent_components_not_grouped(self) -> None:
        """Name components that are far apart should not be grouped."""
        detector = MockDetector(
            entities=[
                PIIEntity(
                    type=PIIType.NAME_FIRST,
                    value="John",
                    start=0,
                    end=4,
                    confidence=0.9,
                ),
                # This is far from the previous entity
                PIIEntity(
                    type=PIIType.NAME_LAST,
                    value="Smith",
                    start=50,
                    end=55,
                    confidence=0.9,
                ),
            ]
        )
        loop = PIILoop(detector=detector)
        
        text = "John mentioned something about the project. Mr. Smith agreed."
        redacted, state = loop.redact(text)
        
        # These should be treated as separate people
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_2]" in state.tokens  # Different index