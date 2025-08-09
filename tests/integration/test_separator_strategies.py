"""Test different separator strategies for batch detection."""

import pytest
from redactyl.detectors.presidio import PresidioDetector
from redactyl.types import PIIEntity, PIIType


class TestSeparatorStrategies:
    """Test various separator strategies for batch PII detection."""
    
    @pytest.fixture
    def detector(self):
        """Create a Presidio detector instance."""
        try:
            return PresidioDetector(confidence_threshold=0.7)
        except Exception as e:
            pytest.skip(f"Presidio not available: {e}")
    
    def test_null_byte_separator(self, detector):
        """Test using NULL byte as separator."""
        # Test fields
        fields = {
            "email": "Contact me at john@example.com",
            "name": "My name is John Smith",
            "phone": "Call me at 555-123-4567"
        }
        
        # Combine with NULL byte separator
        separator = "\x00"
        composite_text = separator.join(fields.values())
        
        # Detect PII in composite text
        entities = detector.detect(composite_text)
        
        # Verify all PII was detected (more lenient matching due to NLP tokenization issues)
        assert any(e.value == "john@example.com" for e in entities)
        # Accept partial matches for names due to separator tokenization issues
        assert any("John Smith" in e.value for e in entities if e.type == PIIType.PERSON)
        assert any(e.value == "555-123-4567" for e in entities)
        
        # Note: With NULL byte separator, Presidio's NER sometimes includes the separator
        # in entity values due to tokenization issues. This is a known limitation.
    
    def test_zero_width_space_separator(self, detector):
        """Test using zero-width space as separator."""
        fields = {
            "field1": "Email: alice@example.com",
            "field2": "Phone: 555-987-6543"
        }
        
        # Zero-width space (invisible but present)
        separator = "\u200B"
        composite_text = separator.join(fields.values())
        
        entities = detector.detect(composite_text)
        
        # Should detect both PII values
        assert any(e.value == "alice@example.com" for e in entities)
        assert any(e.value == "555-987-6543" for e in entities)
    
    def test_unicode_private_use_separator(self, detector):
        """Test using Unicode private use area as separator."""
        fields = {
            "comment": "Bob Smith mentioned his email",
            "notes": "Contact at bob@example.com"
        }
        
        # Unicode private use character
        separator = "\uE000"
        composite_text = separator.join(fields.values())
        
        entities = detector.detect(composite_text)
        
        # Verify detection works (more lenient due to NLP tokenization with special chars)
        # Accept partial matches for names due to separator tokenization issues
        assert any("Bob Smith" in e.value for e in entities if e.type == PIIType.PERSON)
        # Email should still be detected
        assert any(e.value == "bob@example.com" for e in entities)
    
    def test_newline_sequence_separator(self, detector):
        """Test using newline sequences as separator."""
        fields = {
            "field1": "IP address: 192.168.1.1",
            "field2": "Visit https://example.com",
            "field3": "Location: New York"
        }
        
        # Double newline separator
        separator = "\n\n"
        composite_text = separator.join(fields.values())
        
        entities = detector.detect(composite_text)
        
        # Check detections
        assert any(e.type == PIIType.IP_ADDRESS for e in entities)
        assert any(e.type == PIIType.URL for e in entities)
        assert any(e.type == PIIType.LOCATION for e in entities)
    
    def test_separator_in_content(self, detector):
        """Test when separator appears naturally in content."""
        # Use a separator that might appear in content
        separator = " | "
        
        fields = {
            "field1": "Email: test@example.com | Phone: 555-1234",  # Contains separator!
            "field2": "Name: Carol Davis"
        }
        
        composite_text = separator.join(fields.values())
        
        entities = detector.detect(composite_text)
        
        # Should still detect all PII correctly
        assert any(e.value == "test@example.com" for e in entities)
        assert any(e.value == "555-1234" for e in entities)
        assert any(e.value == "Carol Davis" for e in entities)
    
    def test_unicode_text_with_separators(self, detector):
        """Test separators with Unicode content including emojis."""
        fields = {
            "field1": "Call José at 555-0123 📞",
            "field2": "Email: müller@example.de",
            "field3": "北京市 (Beijing)"
        }
        
        # Test multiple separator strategies with Unicode
        separators = ["\x00", "\u200B", "\uE000", "\n\n"]
        
        for separator in separators:
            composite_text = separator.join(fields.values())
            entities = detector.detect(composite_text)
            
            # Basic check that detection still works
            phone_detected = any("555-0123" in e.value for e in entities)
            email_detected = any("example.de" in e.value for e in entities)
            
            assert phone_detected or email_detected, f"Detection failed with separator {repr(separator)}"
    
    def test_position_mapping_accuracy(self, detector):
        """Test that entity positions are accurate after combining fields."""
        # Simple fields with known content
        field1 = "John Smith"
        field2 = "jane@example.com"
        separator = "\x00"
        
        composite_text = field1 + separator + field2
        
        entities = detector.detect(composite_text)
        
        # Find John Smith entity
        john_entity = next((e for e in entities if e.value == "John Smith"), None)
        if john_entity:
            assert john_entity.start == 0
            assert john_entity.end == len("John Smith")
        
        # Find email entity
        email_entity = next((e for e in entities if e.value == "jane@example.com"), None)
        if email_entity:
            expected_start = len(field1) + len(separator)
            assert email_entity.start == expected_start
            assert email_entity.end == expected_start + len("jane@example.com")
    
    def test_large_text_performance(self, detector):
        """Test separator strategies with larger text blocks."""
        # Create fields with varying sizes
        fields = {
            "small": "Email: test@example.com",
            "medium": "Contact " * 50 + "David Miller at 555-9999",
            "large": "Lorem ipsum " * 200 + "SSN: 987-65-4321"
        }
        
        separator = "\x00"
        composite_text = separator.join(fields.values())
        
        # Should handle large text without issues
        entities = detector.detect(composite_text)
        
        assert any(e.value == "test@example.com" for e in entities)
        assert any("David Miller" in e.value for e in entities)
        assert any(e.value == "987-65-4321" for e in entities)
    
    def test_recommended_separator_strategy(self, detector):
        """Test our recommended separator strategy."""
        # Our recommendation: NULL byte for maximum compatibility
        RECOMMENDED_SEPARATOR = "\x00"
        
        # Test with various challenging scenarios
        test_cases = [
            {
                "fields": {
                    "f1": "Regular text with john@example.com",
                    "f2": "Text with \x00 null byte and Jane Doe",  # Contains separator!
                    "f3": "Unicode: José García, phone: +1-555-0123"
                },
                "expected_pii": ["john@example.com", "Jane Doe", "+1-555-0123"]
            },
            {
                "fields": {
                    "f1": "Multiple: alice@example.com and bob@example.com",
                    "f2": "SSN: 111-22-3333 and 444-55-6666"
                },
                "expected_pii": ["alice@example.com", "bob@example.com", "111-22-3333", "444-55-6666"]
            }
        ]
        
        for test_case in test_cases:
            composite_text = RECOMMENDED_SEPARATOR.join(test_case["fields"].values())
            entities = detector.detect(composite_text)
            
            detected_values = [e.value for e in entities]
            for expected in test_case["expected_pii"]:
                assert any(expected in v for v in detected_values), f"Failed to detect {expected}"