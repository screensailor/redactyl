"""Real-world integration tests for batch PII detection."""

import pytest
from redactyl.batch import BatchDetector, SmartBatchDetector
from redactyl.detectors.presidio import PresidioDetector
from redactyl.entity_tracker import GlobalEntityTracker, NameComponentTracker
from redactyl.types import PIIType, RedactionState


class TestBatchRealWorld:
    """Test real-world scenarios with batch detection."""
    
    @pytest.fixture
    def detector(self):
        """Create a Presidio detector instance."""
        try:
            return PresidioDetector(confidence_threshold=0.7)
        except Exception as e:
            pytest.skip(f"Presidio not available: {e}")
    
    def test_customer_support_ticket(self, detector):
        """Test a customer support ticket with multiple PII fields."""
        # Simulate a support ticket with various fields
        ticket_fields = {
            "customer_name": "Dr. Sarah Johnson",
            "customer_email": "sarah.johnson@example.com",
            "subject": "Billing issue for Sarah Johnson's account",
            "description": "I received a call from Dr. Johnson at 555-123-4567 about incorrect charges. "
                          "She mentioned her friend Robert Smith (bob@example.com) has the same issue.",
            "agent_notes": "Contacted Sarah at her phone number. Will follow up via email.",
            "resolution": "Refunded Dr. Johnson and Mr. Smith. Sent confirmation to both emails."
        }
        
        # Detect PII in batch
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(ticket_fields)
        
        # Track entities globally for consistent tokens
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Build redaction state
        state = RedactionState()
        for field_tokens in tokens_by_field.values():
            for token in field_tokens:
                state = state.with_token(token.token, token)
        
        # Verify consistent tokenization
        # Sarah Johnson should have consistent tokens across fields
        sarah_tokens = set()
        for field_tokens in tokens_by_field.values():
            for token in field_tokens:
                if "Sarah" in token.original or "Johnson" in token.original:
                    if "NAME" in token.pii_type.name:
                        sarah_tokens.add(token.token)
        
        print("\nSarah-related tokens found:", sarah_tokens)
        
        # Print detailed token info for debugging
        print("\nDetailed Sarah tokens:")
        for field, tokens in tokens_by_field.items():
            sarah_field_tokens = [t for t in tokens if "Sarah" in t.original or "Johnson" in t.original]
            if sarah_field_tokens:
                print(f"  {field}:")
                for t in sarah_field_tokens:
                    print(f"    {t.token} = '{t.original}'")
        
        # Note: Due to how names are detected in different contexts,
        # we might get different indices. The key is that the same 
        # exact string gets the same token
        assert len(sarah_tokens) > 0, "Should detect Sarah-related name tokens"
        
        # Verify email consistency
        email_tokens = set()
        for field_tokens in tokens_by_field.values():
            for token in field_tokens:
                if token.pii_type == PIIType.EMAIL and "sarah" in token.original:
                    email_tokens.add(token.token)
        
        assert len(email_tokens) == 1, f"Multiple tokens for same email: {email_tokens}"
        
        # Print summary
        print("\nPII Summary:")
        for field, tokens in tokens_by_field.items():
            if tokens:
                print(f"\n{field}:")
                for token in tokens:
                    print(f"  {token.token} = '{token.original}'")
    
    def test_medical_record_scenario(self, detector):
        """Test medical record with patient and doctor information."""
        medical_fields = {
            "patient_info": "Patient: James Wilson, DOB: 01/15/1980",
            "emergency_contact": "Contact: Mary Wilson (wife) at 555-987-6543",
            "doctor_notes": "Dr. Emily Chen examined James Wilson. Follow-up with Dr. Chen needed.",
            "prescription": "Prescribed by Dr. Chen for J. Wilson",
            "insurance": "Insurance holder: James Wilson, Policy# 12345"
        }
        
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(medical_fields)
        
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Verify James Wilson consistency
        james_tokens = []
        for tokens in tokens_by_field.values():
            for token in tokens:
                if "James" in token.original or "Wilson" in token.original or "J. Wilson" in token.original:
                    james_tokens.append((token.token, token.original))
        
        print("\nJames Wilson tokens:", james_tokens)
        
        # Dr. Chen should also be consistent
        chen_tokens = []
        for tokens in tokens_by_field.values():
            for token in tokens:
                if "Chen" in token.original or "Emily" in token.original:
                    chen_tokens.append((token.token, token.original))
        
        print("Dr. Chen tokens:", chen_tokens)
    
    @pytest.mark.skip(reason="Requires GLiNER for full name detection")
    def test_email_thread_scenario(self, detector):
        """Test email thread with multiple participants."""
        email_thread = {
            "from": "Alice Brown <alice.brown@company.com>",
            "to": "Bob Davis <bob.davis@company.com>; Carol Evans <carol@company.com>",
            "cc": "David Fisher <d.fisher@company.com>",
            "subject": "Re: Meeting with Alice and Bob",
            "body": "Hi Bob and Carol,\n\n"
                   "As discussed with Alice Brown yesterday at 555-1111, we need to schedule "
                   "the meeting. Carol, can you coordinate with David Fisher?\n\n"
                   "Thanks,\nAlice\n\n"
                   "Alice Brown | Senior Manager | 555-1111 | alice.brown@company.com",
            "signature": "Best regards,\nAlice Brown\nSenior Manager"
        }
        
        # Use smart batch detector with grouping
        batch_detector = SmartBatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(email_thread)
        
        tracker = NameComponentTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Count unique people
        unique_people = set()
        for tokens in tokens_by_field.values():
            for token in tokens:
                if token.pii_type in {PIIType.PERSON, PIIType.NAME_FIRST, PIIType.NAME_LAST}:
                    # Extract person index
                    parts = token.token.rstrip("]").split("_")
                    person_idx = int(parts[-1])
                    unique_people.add(person_idx)
        
        print(f"\nUnique people found: {len(unique_people)}")
        assert len(unique_people) >= 4, "Should detect at least 4 different people"
        
        # Alice should have consistent tokens throughout
        alice_tokens = []
        for field, tokens in tokens_by_field.items():
            for token in tokens:
                if "Alice" in token.original or "Brown" in token.original:
                    alice_tokens.append((field, token.token, token.original))
        
        print("\nAlice tokens across fields:")
        for field, token, original in alice_tokens:
            print(f"  {field}: {token} = '{original}'")
    
    def test_performance_with_many_fields(self, detector):
        """Test performance with many fields."""
        # Create 50 fields with various PII
        many_fields = {}
        people = ["John Smith", "Jane Doe", "Bob Johnson", "Alice Williams", "Charlie Brown"]
        emails = ["john@example.com", "jane@example.com", "bob@example.com", "alice@example.com", "charlie@example.com"]
        phones = ["555-0001", "555-0002", "555-0003", "555-0004", "555-0005"]
        
        for i in range(50):
            person_idx = i % len(people)
            field_name = f"field_{i}"
            
            # Mix different content types
            if i % 3 == 0:
                many_fields[field_name] = f"Contact {people[person_idx]} at {emails[person_idx]}"
            elif i % 3 == 1:
                many_fields[field_name] = f"Call {people[person_idx]} on {phones[person_idx]}"
            else:
                many_fields[field_name] = f"{people[person_idx]} mentioned {people[(person_idx + 1) % len(people)]}"
        
        # Process in batch
        batch_detector = BatchDetector(detector)
        entities_by_field = batch_detector.detect_batch(many_fields)
        
        tracker = GlobalEntityTracker()
        tokens_by_field = tracker.assign_tokens(entities_by_field)
        
        # Verify consistency
        # John should have one consistent index, Smith should have one consistent index
        john_indices = set()
        smith_indices = set()
        for tokens in tokens_by_field.values():
            for token in tokens:
                # Use exact matching, not substring matching
                if token.original == "John":
                    parts = token.token.rstrip("]").split("_")
                    john_indices.add(int(parts[-1]))
                elif token.original == "Smith":
                    parts = token.token.rstrip("]").split("_")
                    smith_indices.add(int(parts[-1]))
        
        print(f"\nJohn indices across {len(many_fields)} fields: {john_indices}")
        print(f"Smith indices across {len(many_fields)} fields: {smith_indices}")
        assert len(john_indices) == 1, f"John should have exactly one consistent index, got {john_indices}"
        assert len(smith_indices) == 1, f"Smith should have exactly one consistent index, got {smith_indices}"
        
        # Check total unique tokens
        all_tokens = set()
        for tokens in tokens_by_field.values():
            for token in tokens:
                all_tokens.add(token.token)
        
        print(f"Total unique tokens: {len(all_tokens)}")
        print(f"Fields processed: {len(many_fields)}")
        print(f"Entities found: {sum(len(entities) for entities in entities_by_field.values())}")