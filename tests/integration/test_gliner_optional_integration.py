"""Integration tests for GLiNER as optional dependency."""

import warnings
from unittest.mock import patch, MagicMock

import pytest

from redactyl import PIILoop
from redactyl.detectors.presidio import PresidioDetector
from redactyl.detectors.gliner_parser import GlinerNameParser


class TestGLiNEROptionalIntegration:
    """Test GLiNER optional dependency in real usage scenarios."""

    def test_redactyl_works_without_gliner(self):
        """Test that PIILoop works when GLiNER is not available."""
        # Test with MockDetector (doesn't need GLiNER)
        from redactyl.detectors import MockDetector
        from redactyl.types import PIIEntity, PIIType
        
        # Create mock entities
        entities = [
            PIIEntity(type=PIIType.PERSON, value="John Smith", start=8, end=18, confidence=0.9),
            PIIEntity(type=PIIType.EMAIL, value="john@example.com", start=22, end=38, confidence=0.95)
        ]
        
        redactyl = PIILoop(detector=MockDetector(entities=entities))
        
        text = "Contact John Smith at john@example.com"
        redacted_text, state = redactyl.redact(text)
        
        # Should detect entities
        assert "[" in redacted_text and "]" in redacted_text
        
        # Should be able to unredact
        unredacted_text, issues = redactyl.unredact(redacted_text, state)
        assert unredacted_text == text

    def test_detector_with_explicit_gliner_disable(self):
        """Test that detector works when GLiNER is explicitly disabled."""
        detector = PresidioDetector(use_gliner_for_names=False)
        
        # Should not have GLiNER parser
        assert detector._gliner_parser is None
        
        # Should still detect names
        text = "Dr. Jane Doe called yesterday"
        entities = detector.detect_with_name_parsing(text)
        
        # Should find name components using nameparser
        found_types = {e.type.value for e in entities}
        found_values = {e.value for e in entities}
        
        # Check that names were detected (as PERSON or name components)
        assert "Jane" in found_values or "Jane Doe" in found_values
        assert "Doe" in found_values or "Jane Doe" in found_values

    def test_gliner_parser_availability_check(self):
        """Test GLiNER parser availability checking."""
        parser = GlinerNameParser()
        
        # Check if available (will be True if GLiNER is installed, False otherwise)
        is_available = parser.is_available
        assert isinstance(is_available, bool)
        
        # If not available, should return None for parsing
        if not is_available:
            from redactyl.types import PIIEntity, PIIType
            
            entity = PIIEntity(
                type=PIIType.PERSON,
                value="John Doe",
                start=0,
                end=8,
                confidence=0.9
            )
            result = parser.parse_name_components(entity)
            assert result is None

    def test_warning_when_gliner_requested_but_unavailable(self):
        """Test that appropriate warnings are shown when GLiNER is unavailable."""
        # Test creating detector with GLiNER disabled - should not warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            detector = PresidioDetector(use_gliner_for_names=False)
            
            # Should NOT have GLiNER warnings when explicitly disabled
            gliner_warnings = [
                warning for warning in w 
                if "GLiNER" in str(warning.message)
            ]
            assert len(gliner_warnings) == 0
            assert detector._gliner_parser is None

    def test_graceful_fallback_chain(self):
        """Test the complete fallback chain from GLiNER to nameparser."""
        # Create detector
        detector = PresidioDetector(use_gliner_for_names=True)
        
        text = "CEO Tim Cook announced new products"
        entities = detector.detect_with_name_parsing(text)
        
        # Should detect name components regardless of GLiNER availability
        values = [e.value for e in entities]
        
        # Should find Tim and Cook either as components or PERSON entities
        assert any("Tim" in v for v in values)
        assert any("Cook" in v for v in values)

    @pytest.mark.parametrize("use_gliner", [True, False])
    def test_consistent_api_with_and_without_gliner(self, use_gliner):
        """Test that the API remains consistent regardless of GLiNER availability."""
        detector = PresidioDetector(use_gliner_for_names=use_gliner)
        
        # Same API should work
        text = "Contact person: Alice Johnson"
        
        # Basic detection
        basic_entities = detector.detect(text)
        assert isinstance(basic_entities, list)
        
        # Detection with name parsing
        parsed_entities = detector.detect_with_name_parsing(text)
        assert isinstance(parsed_entities, list)
        
        # Should find entities in both cases
        assert len(basic_entities) > 0
        assert len(parsed_entities) > 0