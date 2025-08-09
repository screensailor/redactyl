"""Tests for PIIEntity data structure."""

import pytest
from redactyl.types import PIIEntity, PIIType


class TestPIIEntity:
    """Test PIIEntity data structure and validation."""
    
    def test_create_valid_entity(self):
        """Test creating a valid PII entity."""
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="john@example.com",
            start=10,
            end=26,
            confidence=0.95
        )
        
        assert entity.type == PIIType.EMAIL
        assert entity.value == "john@example.com"
        assert entity.start == 10
        assert entity.end == 26
        assert entity.confidence == 0.95
    
    def test_entity_immutability(self):
        """Test that PIIEntity is immutable."""
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="John Doe",
            start=0,
            end=8,
            confidence=0.9
        )
        
        with pytest.raises(AttributeError):
            entity.value = "Jane Doe"
        
        with pytest.raises(AttributeError):
            entity.start = 5
    
    def test_invalid_start_position(self):
        """Test that negative start position raises error."""
        with pytest.raises(ValueError, match="Start position must be non-negative"):
            PIIEntity(
                type=PIIType.PHONE,
                value="555-1234",
                start=-1,
                end=8,
                confidence=0.9
            )
    
    def test_invalid_end_position(self):
        """Test that end <= start raises error."""
        with pytest.raises(ValueError, match="End position must be greater than start"):
            PIIEntity(
                type=PIIType.ADDRESS,
                value="123 Main St",
                start=10,
                end=10,
                confidence=0.9
            )
        
        with pytest.raises(ValueError, match="End position must be greater than start"):
            PIIEntity(
                type=PIIType.ADDRESS,
                value="123 Main St",
                start=10,
                end=5,
                confidence=0.9
            )
    
    def test_invalid_confidence(self):
        """Test that confidence outside [0,1] raises error."""
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            PIIEntity(
                type=PIIType.SSN,
                value="123-45-6789",
                start=0,
                end=11,
                confidence=1.5
            )
        
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            PIIEntity(
                type=PIIType.SSN,
                value="123-45-6789",
                start=0,
                end=11,
                confidence=-0.1
            )
    
    def test_empty_value(self):
        """Test that empty value raises error."""
        with pytest.raises(ValueError, match="Value cannot be empty"):
            PIIEntity(
                type=PIIType.CUSTOM,
                value="",
                start=0,
                end=1,
                confidence=0.9
            )
    
    def test_name_component_types(self):
        """Test name component PII types."""
        first_name = PIIEntity(
            type=PIIType.NAME_FIRST,
            value="Jane",
            start=0,
            end=4,
            confidence=0.95
        )
        
        last_name = PIIEntity(
            type=PIIType.NAME_LAST,
            value="Doe",
            start=5,
            end=8,
            confidence=0.95
        )
        
        assert first_name.type == PIIType.NAME_FIRST
        assert last_name.type == PIIType.NAME_LAST
    
    def test_equality(self):
        """Test entity equality."""
        entity1 = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.9
        )
        
        entity2 = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.9
        )
        
        entity3 = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.8  # Different confidence
        )
        
        assert entity1 == entity2
        assert entity1 != entity3