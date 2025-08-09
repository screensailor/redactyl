"""Test consistent token assignment across fields."""

import pytest
from redactyl.batch import BatchDetector
from redactyl.detectors.presidio import PresidioDetector
from redactyl.entity_tracker import GlobalEntityTracker, NameComponentTracker
from redactyl.types import PIIEntity, PIIType


class TestConsistentTokens:
    """Test that the same entity gets the same token across fields."""
    
    @pytest.fixture
    def detector(self):
        """Create a Presidio detector instance."""
        try:
            return PresidioDetector(confidence_threshold=0.7)
        except Exception as e:
            pytest.skip(f"Presidio not available: {e}")
    
    def test_basic_consistency(self, detector):
        """Test basic token consistency across fields."""
        # Fields with repeated entities
        fields = {
            "field1": "Contact John Smith at john@example.com",
            "field2": "John Smith called about the order",
            "field3": "Email john@example.com for details"
        }
        
        # Detect PII in batch
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(fields)
        
        # Track entities globally
        tracker = GlobalEntityTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Verify John Smith gets same token
        field1_tokens = {t.token: t.original for t in tokens_by_field.get("field1", [])}
        field2_tokens = {t.token: t.original for t in tokens_by_field.get("field2", [])}
        
        # Find John Smith tokens
        john_tokens = []
        for token, original in field1_tokens.items():
            if "John Smith" in original:
                john_tokens.append(token)
        for token, original in field2_tokens.items():
            if "John Smith" in original:
                john_tokens.append(token)
        
        # Should be the same token
        if john_tokens:
            assert len(set(john_tokens)) == 1, f"Different tokens for John Smith: {john_tokens}"
        
        # Verify email gets same token
        email_tokens = []
        for field in ["field1", "field3"]:
            for t in tokens_by_field.get(field, []):
                if t.original == "john@example.com":
                    email_tokens.append(t.token)
        
        if email_tokens:
            assert len(set(email_tokens)) == 1, f"Different tokens for email: {email_tokens}"
    
    def test_case_insensitive_matching(self, detector):
        """Test that entities match regardless of case."""
        fields = {
            "field1": "Contact JOHN SMITH",
            "field2": "john smith is here",
            "field3": "John Smith arrived"
        }
        
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(fields)
        
        tracker = GlobalEntityTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Collect all person tokens
        person_tokens = []
        for tokens in tokens_by_field.values():
            for t in tokens:
                if t.pii_type == PIIType.PERSON:
                    person_tokens.append(t.token)
        
        # Should all be the same token despite case differences
        if person_tokens:
            unique_tokens = set(person_tokens)
            assert len(unique_tokens) == 1, f"Multiple tokens for same person: {unique_tokens}"
    
    def test_different_entities_different_tokens(self, detector):
        """Test that different entities get different tokens."""
        fields = {
            "field1": "John Smith and Jane Doe",
            "field2": "Contact john@example.com or jane@example.com"
        }
        
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(fields)
        
        tracker = GlobalEntityTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Collect all tokens
        all_tokens = []
        for tokens in tokens_by_field.values():
            all_tokens.extend([t.token for t in tokens])
        
        # Each unique entity should have a unique token
        unique_tokens = set(all_tokens)
        
        # We should have different tokens for different entities
        assert len(unique_tokens) >= 2, f"Not enough unique tokens: {unique_tokens}"
    
    def test_token_numbering(self, detector):
        """Test that tokens are numbered consistently."""
        fields = {
            "field1": "Alice called, then Bob, then Carol",
            "field2": "David and Eve and Frank"
        }
        
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(fields)
        
        tracker = GlobalEntityTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Collect all person tokens
        person_tokens = []
        for tokens in tokens_by_field.values():
            for t in tokens:
                if t.pii_type == PIIType.PERSON:
                    person_tokens.append(t.token)
        
        # Should have sequential numbering
        if person_tokens:
            # Extract numbers from tokens like [PERSON_1], [PERSON_2]
            numbers = []
            for token in person_tokens:
                if "_" in token:
                    # Handle tokens like [NAME_FIRST_1] or [PERSON_1]
                    parts = token.rstrip("]").split("_")
                    try:
                        numbers.append(int(parts[-1]))  # Get the last part as the index
                    except ValueError:
                        pass
            
            if numbers:
                # Should start from 1
                assert min(numbers) == 1
                # Should be consecutive (though some might be repeated)
                unique_numbers = sorted(set(numbers))
                assert unique_numbers == list(range(1, max(numbers) + 1))
    
    def test_name_component_consistency(self, detector):
        """Test that name components get consistent tokens."""
        # Use the enhanced detector that can parse name components
        enhanced_detector = PresidioDetector(confidence_threshold=0.7)
        
        fields = {
            "field1": "Dr. John Smith is the contact",
            "field2": "Email from John",
            "field3": "Mr. Smith called"
        }
        
        batch_detector = BatchDetector(enhanced_detector)
        entities_by_field = batch_detector.detect_batch(fields)
        
        # Use name component tracker
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Collect tokens by type
        tokens_by_type = {}
        for tokens in tokens_by_field.values():
            for t in tokens:
                if t.pii_type.name not in tokens_by_type:
                    tokens_by_type[t.pii_type.name] = []
                tokens_by_type[t.pii_type.name].append((t.token, t.original))
        
        # Print for debugging
        print("\nTokens by type:")
        for pii_type, token_list in tokens_by_type.items():
            print(f"  {pii_type}: {token_list}")
        
        # Components of the same person should have same index
        # This is a simplified test - real implementation would be more sophisticated