"""Test that the batch detector correctly handles content patterns with double newlines."""

import pytest
from redactyl.batch import BatchDetector, SmartBatchDetector
from redactyl.detectors.presidio import PresidioDetector
from redactyl.types import PIIType


class TestContentPatternHandling:
    """Test suite for content pattern handling with double newlines."""
    
    @pytest.fixture
    def detector(self):
        """Create a Presidio detector instance."""
        try:
            return PresidioDetector(confidence_threshold=0.7)
        except Exception as e:
            pytest.skip(f"Presidio not available: {e}")
    
    def test_double_newline_in_content(self, detector):
        """Test that double newlines in content don't break detection."""
        # Typical content with double newlines
        fields = {
            "news_article": """
Breaking News: CEO John Smith announced today.

In a press conference, Smith stated that the company is expanding.

Contact: john.smith@company.com
""",
            "chat_transcript": """
User: Hi, I'm Jane Doe

Agent: Hello Jane! How can I help you today?

User: My email is jane.doe@example.com

Agent: Thank you, I've noted your email.
""",
            "email_content": """
Dear Bob Johnson,

Thank you for your inquiry.

Please contact us at support@company.com or call 555-123-4567.

Best regards,
Sarah Williams
sarah.williams@company.com
"""
        }
        
        # Test with position-based tracking (new default)
        batch_detector = BatchDetector(detector, use_position_tracking=True)
        
        # This should work without issues
        entities_by_field = batch_detector.detect_batch(fields)
        
        # Verify entities were detected correctly
        assert "news_article" in entities_by_field
        assert "chat_transcript" in entities_by_field
        assert "email_content" in entities_by_field
        
        # Check that entities are correctly mapped to their fields
        for field_path, entities in entities_by_field.items():
            field_text = fields[field_path]
            for entity in entities:
                # Verify the extracted text matches the detected value
                extracted = field_text[entity.start:entity.end]
                assert extracted == entity.value, (
                    f"Position mismatch in {field_path}: "
                    f"expected '{entity.value}', got '{extracted}'"
                )
    
    def test_position_tracking_vs_legacy(self, detector):
        """Compare position tracking with legacy boundary marker mode."""
        # Content with potential separator conflicts
        fields = {
            "field1": "Contact: john@example.com\n\nNote: Important",
            "field2": "Email jane@example.com | Phone: 555-1234",
            "field3": "Name: Bob Smith\uE000Special character test"
        }
        
        # Test position-based (recommended)
        pos_detector = BatchDetector(detector, use_position_tracking=True)
        pos_results = pos_detector.detect_batch(fields)
        
        # Test boundary marker mode (legacy)
        boundary_detector = BatchDetector(detector, use_position_tracking=False)
        boundary_results = boundary_detector.detect_batch(fields)
        
        # Both should detect entities, but position-based is safer
        assert len(pos_results) > 0, "Position tracking should detect entities"
        assert len(boundary_results) > 0, "Boundary markers should detect entities"
        
        # Verify position accuracy for both
        for results in [pos_results, boundary_results]:
            for field_path, entities in results.items():
                field_text = fields[field_path]
                for entity in entities:
                    extracted = field_text[entity.start:entity.end]
                    assert extracted == entity.value
    
    def test_smart_batch_detector_default(self, detector):
        """Test that SmartBatchDetector always uses position tracking."""
        # Content with double newlines
        fields = {
            "message": "Hello,\n\nMy name is Alice Brown.\n\nEmail: alice@example.com"
        }
        
        # SmartBatchDetector should handle this without issues
        smart_detector = SmartBatchDetector(detector)
        results = smart_detector.detect_batch(fields)
        
        assert "message" in results
        entities = results["message"]
        
        # Verify detected entities
        emails = [e for e in entities if e.type == PIIType.EMAIL]
        assert len(emails) > 0, "Should detect email"
        
        # Verify position accuracy
        field_text = fields["message"]
        for entity in entities:
            extracted = field_text[entity.start:entity.end]
            assert extracted == entity.value
    
    def test_empty_fields_handling(self, detector):
        """Test handling of empty fields in batch detection."""
        fields = {
            "field1": "John Smith",
            "field2": "",  # Empty field
            "field3": "jane@example.com",
            "field4": None,  # Will be skipped
        }
        
        # Remove None values
        fields = {k: v for k, v in fields.items() if v is not None}
        
        batch_detector = BatchDetector(detector, use_position_tracking=True)
        results = batch_detector.detect_batch(fields)
        
        # Should only have results for non-empty fields
        assert "field1" in results or "field3" in results
        assert "field2" not in results  # Empty field should have no entities
    
    def test_unicode_and_special_chars(self, detector):
        """Test handling of Unicode and special characters."""
        fields = {
            "field1": "Contact José García at jose@ejemplo.es",
            "field2": "北京办公室: beijing@company.cn",
            "field3": "Email: müller@beispiel.de 📧",
            "field4": "Call us: +1-555-0123 ☎️"
        }
        
        batch_detector = BatchDetector(detector, use_position_tracking=True)
        results = batch_detector.detect_batch(fields)
        
        # Verify position accuracy with Unicode
        for field_path, entities in results.items():
            field_text = fields[field_path]
            for entity in entities:
                extracted = field_text[entity.start:entity.end]
                assert extracted == entity.value, (
                    f"Unicode position issue in {field_path}: "
                    f"expected '{entity.value}', got '{extracted}'"
                )
    
    def test_no_word_fusion_between_fields(self, detector):
        """Test that field values are not fused together when concatenated."""
        # Fields that end and start with names - potential fusion risk
        fields = {
            "sender": "Message from John Smith",  # Ends with "Smith"
            "recipient": "Jane Doe received this",  # Starts with "Jane"
            "cc": "Bob Johnson was copied",  # Starts with "Bob"
            "subject": "Meeting with Alice Brown"  # Ends with "Brown"
        }
        
        # Test with position-based tracking (uses newline separator)
        batch_detector = BatchDetector(detector, use_position_tracking=True)
        results = batch_detector.detect_batch(fields)
        
        # Collect all detected names
        all_detected_names = []
        for entities in results.values():
            for entity in entities:
                if entity.type in [PIIType.PERSON, PIIType.NAME_FIRST, PIIType.NAME_LAST]:
                    all_detected_names.append(entity.value)
        
        # Verify names are detected as separate entities, not fused
        # The key test: if word fusion occurred, we'd see things like "SmithJane" or "BrownBob"
        # Let's check that individual names are detected (showing they weren't fused)
        print(f"Detected names: {all_detected_names}")
        
        # Check that we have individual name components detected
        assert "John" in all_detected_names, "John should be detected"
        assert "Jane" in all_detected_names or "Doe" in all_detected_names, "Jane or Doe should be detected"
        assert "Bob" in all_detected_names or "Johnson" in all_detected_names, "Bob or Johnson should be detected"
        assert "Alice" in all_detected_names or "Brown" in all_detected_names, "Alice or Brown should be detected"
        
        # Most importantly, verify no fused names exist
        for name in all_detected_names:
            assert "SmithJane" not in name, f"Found fused name: {name}"
            assert "DoeeBob" not in name, f"Found fused name: {name}"
            assert "JohnsonAlice" not in name, f"Found fused name: {name}"
            assert "BrownMessage" not in name, f"Found fused name: {name}"
        
        # Also test with boundary-based approach
        batch_detector_boundary = BatchDetector(detector, use_position_tracking=False)
        results_boundary = batch_detector_boundary.detect_batch(fields)
        
        # Verify boundary approach also doesn't fuse
        boundary_names = []
        for entities in results_boundary.values():
            for entity in entities:
                if entity.type in [PIIType.PERSON, PIIType.NAME_FIRST, PIIType.NAME_LAST]:
                    boundary_names.append(entity.value)
        
        # Check no fusion in boundary approach either
        for name in boundary_names:
            assert "SmithJane" not in name, f"Boundary approach fused: {name}"
            assert "DoeBob" not in name, f"Boundary approach fused: {name}"