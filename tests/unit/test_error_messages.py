"""Test clear error messages for various failure scenarios."""

import pytest
from redactyl.batch import BatchDetector
from redactyl.detectors.mock import MockDetector
from redactyl.exceptions import (
    BatchDetectionError, 
    UnredactionError, 
    TokenizationError,
    ConfigurationError,
    NameParsingError
)
from redactyl.types import PIIEntity, PIIType


class TestErrorMessages:
    """Test that error messages are clear and helpful."""
    
    def test_batch_detection_error_with_separator_issue(self):
        """Test error message when separator appears in content."""
        # Create a detector that will fail
        class FailingDetector(MockDetector):
            def detect(self, text: str) -> list[PIIEntity]:
                raise ValueError("Simulated detection failure")
        
        detector = FailingDetector([])
        batch_detector = BatchDetector(detector)
        
        # Fields with separator in content
        fields = {
            "field1": "Normal content",
            "field2": "Content with ||| separator in it",
            "field3": "More content"
        }
        
        with pytest.raises(BatchDetectionError) as exc_info:
            batch_detector.detect_batch(fields)
        
        error = exc_info.value
        error_str = str(error)
        
        # Check error message components
        assert "Failed to detect PII in batch" in error_str
        assert "Failed fields: field1, field2, field3" in error_str
        assert "Original error: Simulated detection failure" in error_str
    
    def test_batch_detection_error_without_separator_issue(self):
        """Test error message when separator is not the issue."""
        class FailingDetector(MockDetector):
            def detect(self, text: str) -> list[PIIEntity]:
                raise RuntimeError("Network timeout")
        
        detector = FailingDetector([])
        batch_detector = BatchDetector(detector)
        
        fields = {"field1": "Some content", "field2": "More content"}
        
        with pytest.raises(BatchDetectionError) as exc_info:
            batch_detector.detect_batch(fields)
        
        error_str = str(exc_info.value)
        
        # Should not mention separator
        assert "separator appearing" not in error_str
        assert "Original error: Network timeout" in error_str
    
    def test_unredaction_error_suggests_fuzzy(self):
        """Test that unredaction errors suggest fuzzy matching."""
        error = UnredactionError(
            "Failed to unredact tokens",
            unmapped_tokens=["[NAME_2]", "[EMAIL_3]"],
            fuzzy_enabled=False
        )
        
        error_str = str(error)
        
        assert "Failed to unredact tokens" in error_str
        assert "Unmapped tokens: ['[NAME_2]', '[EMAIL_3]']" in error_str
        assert "Enable fuzzy matching with fuzzy=True" in error_str
    
    def test_unredaction_error_with_fuzzy_enabled(self):
        """Test error when fuzzy is already enabled."""
        error = UnredactionError(
            "Still failed with fuzzy matching",
            unmapped_tokens=["[INVALID_TOKEN]"],
            fuzzy_enabled=True
        )
        
        error_str = str(error)
        
        # Should not suggest fuzzy since it's already enabled
        assert "Enable fuzzy matching" not in error_str
    
    def test_tokenization_error_with_conflicts(self):
        """Test tokenization error with conflicting tokens."""
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.9
        )
        
        error = TokenizationError(
            "Multiple tokens assigned to same entity",
            entity=entity,
            conflicting_tokens=["[EMAIL_1]", "[EMAIL_2]"]
        )
        
        error_str = str(error)
        
        assert "Multiple tokens assigned" in error_str
        assert "test@example.com" in error_str
        assert "[EMAIL_1]" in error_str
        assert "[EMAIL_2]" in error_str
    
    def test_configuration_error_with_dependency(self):
        """Test configuration error for missing dependencies."""
        error = ConfigurationError(
            "Presidio analyzer not available",
            missing_dependency="presidio-analyzer"
        )
        
        error_str = str(error)
        
        assert "Presidio analyzer not available" in error_str
        assert "Missing dependency: presidio-analyzer" in error_str
        assert "Install with: pip install presidio-analyzer" in error_str
    
    def test_name_parsing_error_helpful_note(self):
        """Test name parsing error includes helpful context."""
        error = NameParsingError(
            "Failed to parse name components",
            name_value="김철수",  # Korean name
            parse_result={"first": "", "last": ""}
        )
        
        error_str = str(error)
        
        assert "Failed to parse name components" in error_str
        assert "Name value: '김철수'" in error_str
        assert "non-Western names" in error_str
        assert "single names" in error_str
    
    def test_base_exception_inheritance(self):
        """Test that all exceptions inherit from PIILoopError."""
        from redactyl.exceptions import PIILoopError
        
        # All custom exceptions should inherit from base
        assert issubclass(BatchDetectionError, PIILoopError)
        assert issubclass(UnredactionError, PIILoopError)
        assert issubclass(TokenizationError, PIILoopError)
        assert issubclass(ConfigurationError, PIILoopError)
        assert issubclass(NameParsingError, PIILoopError)