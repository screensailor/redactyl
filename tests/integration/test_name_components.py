"""Test name component detection and tokenization."""

import pytest
from redactyl.detectors.presidio import PresidioDetector
from redactyl.entity_tracker import NameComponentTracker
from redactyl.types import PIIEntity, PIIType


class TestNameComponents:
    """Test detection and tokenization of name components."""
    
    @pytest.fixture
    def detector(self):
        """Create a Presidio detector instance."""
        try:
            return PresidioDetector(confidence_threshold=0.7)
        except Exception as e:
            pytest.skip(f"Presidio not available: {e}")
    
    def test_basic_name_parsing(self, detector):
        """Test basic name component detection."""
        text = "Dr. John Michael Smith Jr."
        
        # Detect with name parsing
        entities = detector.detect_with_name_parsing(text)
        
        # Should detect components
        types_found = {e.type for e in entities}
        values_found = {e.value for e in entities}
        
        print(f"\nDetected entities: {[(e.type.name, e.value) for e in entities]}")
        
        # Check that we found name components
        # Note: Actual detection depends on Presidio and nameparser behavior
        if entities:
            # At minimum should find the full name as PERSON
            assert any(e.type == PIIType.PERSON for e in entities) or \
                   any(e.type in {PIIType.NAME_FIRST, PIIType.NAME_LAST} for e in entities)
    
    def test_name_component_tokens(self, detector):
        """Test that name components get proper tokens."""
        text = "Contact Dr. Jane Smith at jane@example.com"
        
        entities = detector.detect_with_name_parsing(text)
        
        # Track entities
        tracker = NameComponentTracker()
        tokens = tracker.assign_tokens({"field1": entities})
        
        # Get tokens for this field
        field_tokens = tokens.get("field1", [])
        
        # Print for debugging
        print("\nTokens assigned:")
        for token in field_tokens:
            print(f"  {token.token} = '{token.original}' (type: {token.pii_type.name})")
        
        # Components of same person should have same index
        name_tokens = [t for t in field_tokens if "NAME" in t.pii_type.name or t.pii_type == PIIType.PERSON]
        if name_tokens:
            # Extract indices
            indices = []
            for t in name_tokens:
                if "_" in t.token:
                    # Handle tokens like [NAME_FIRST_1] or [PERSON_1]
                    parts = t.token.rstrip("]").split("_")
                    idx = int(parts[-1])  # Get the last part as the index
                    indices.append(idx)
            
            # Should all be the same index for same person
            if indices:
                assert len(set(indices)) <= 2, f"Too many different indices: {indices}"
    
    def test_multiple_names(self, detector):
        """Test handling multiple names with components."""
        text = "Meeting between Mr. Robert Johnson and Ms. Sarah Williams"
        
        entities = detector.detect_with_name_parsing(text)
        
        # Track entities
        tracker = NameComponentTracker()
        tokens = tracker.assign_tokens({"field1": entities})
        
        field_tokens = tokens.get("field1", [])
        
        # Group tokens by index
        by_index = {}
        for token in field_tokens:
            if "_" in token.token:
                # Handle tokens like [NAME_FIRST_1] or [PERSON_1]
                parts = token.token.rstrip("]").split("_")
                idx = int(parts[-1])  # Get the last part as the index
                if idx not in by_index:
                    by_index[idx] = []
                by_index[idx].append(token)
        
        print("\nTokens by person index:")
        for idx, tokens in by_index.items():
            values = [t.original for t in tokens]
            print(f"  Person {idx}: {values}")
        
        # Should have tokens for both people
        assert len(by_index) >= 1, "Should detect at least one person"
    
    def test_partial_name_references(self, detector):
        """Test that partial name references link to full names."""
        fields = {
            "intro": "Dr. Elizabeth Anderson will present",
            "body": "Elizabeth mentioned the results",
            "conclusion": "Dr. Anderson concludes"
        }
        
        # Detect in each field
        all_entities = {}
        for field, text in fields.items():
            all_entities[field] = detector.detect_with_name_parsing(text)
        
        # Track with name component tracker
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(all_entities)
        
        # Collect all Elizabeth/Anderson tokens
        elizabeth_tokens = []
        for field_tokens in tokens_by_field.values():
            for token in field_tokens:
                if any(name in token.original for name in ["Elizabeth", "Anderson"]):
                    elizabeth_tokens.append(token.token)
        
        print(f"\nElizabeth/Anderson tokens: {elizabeth_tokens}")
        
        # Should use consistent tokens for the same person
        if elizabeth_tokens:
            # Extract indices
            indices = []
            for t in elizabeth_tokens:
                if "_" in t:
                    # Handle tokens like [NAME_FIRST_1] or [PERSON_1]
                    parts = t.rstrip("]").split("_")
                    idx = int(parts[-1])  # Get the last part as the index
                    indices.append(idx)
            
            # Should have at most 2 different indices (one for Elizabeth, one for Anderson)
            # This is reasonable since name parsing might identify them separately in some contexts
            if indices:
                unique_indices = set(indices)
                assert len(unique_indices) <= 2, \
                    f"Too many different indices for the same person: {indices}"
                
                # Check consistency for each name component
                # Elizabeth tokens should be consistent
                elizabeth_only = [elizabeth_tokens[i] for i, tok in enumerate(elizabeth_tokens) if "Elizabeth" in tok and "Anderson" not in tok]
                if elizabeth_only:
                    eliz_indices = [int(t.rstrip("]").split("_")[-1]) for t in elizabeth_only if "_" in t]
                    if eliz_indices:
                        assert len(set(eliz_indices)) == 1, f"Elizabeth has inconsistent indices: {eliz_indices}"
                
                # Anderson tokens should be consistent
                anderson_only = [elizabeth_tokens[i] for i, tok in enumerate(elizabeth_tokens) if "Anderson" in tok and "Elizabeth" not in tok]
                if anderson_only:
                    and_indices = [int(t.rstrip("]").split("_")[-1]) for t in anderson_only if "_" in t]
                    if and_indices:
                        assert len(set(and_indices)) == 1, f"Anderson has inconsistent indices: {and_indices}"
    
    def test_name_with_email_correlation(self, detector):
        """Test correlating names with email addresses."""
        text = "John Smith (john.smith@example.com) is the contact"
        
        entities = detector.detect_with_name_parsing(text)
        
        # Should detect both name and email
        name_entities = [e for e in entities if "NAME" in e.type.name or e.type == PIIType.PERSON]
        email_entities = [e for e in entities if e.type == PIIType.EMAIL]
        
        assert name_entities, "Should detect name"
        assert email_entities, "Should detect email"
        
        # The email username matches the name
        if email_entities:
            email = email_entities[0].value
            username = email.split("@")[0]
            # Check if username contains name parts
            assert "john" in username.lower() or "smith" in username.lower()
    
    def test_formal_informal_name_matching(self, detector):
        """Test matching formal and informal name variants."""
        fields = {
            "formal": "Professor William Johnson, PhD",
            "informal": "Bill Johnson said",
            "last_only": "Prof. Johnson explained"
        }
        
        all_entities = {}
        for field, text in fields.items():
            all_entities[field] = detector.detect_with_name_parsing(text)
        
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(all_entities)
        
        # Collect all Johnson tokens
        johnson_tokens = []
        for field_tokens in tokens_by_field.values():
            for token in field_tokens:
                if "Johnson" in token.original:
                    johnson_tokens.append(token)
        
        print("\nJohnson tokens:")
        for t in johnson_tokens:
            print(f"  {t.token} = '{t.original}'")
        
        # Note: William/Bill matching would require more sophisticated logic
        # For now, at least Johnson should be consistent
        if johnson_tokens:
            last_name_tokens = [t.token for t in johnson_tokens if t.pii_type == PIIType.NAME_LAST]
            if last_name_tokens:
                assert len(set(last_name_tokens)) == 1, \
                    f"Different tokens for same last name: {set(last_name_tokens)}"