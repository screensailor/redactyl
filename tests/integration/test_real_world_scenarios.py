"""Integration tests for real-world scenarios."""

import json
import pytest
from redactyl import PIIEntity, PIILoop, PIIType, PIISession, RedactionState
from redactyl.detectors.mock import MockDetector


class TestRealWorldScenarios:
    """Test real-world use cases and scenarios."""
    
    def test_name_component_extraction_scenario(self):
        """Test extracting name components from email signatures."""
        # Original email with signature
        entities = [
            PIIEntity(
                type=PIIType.NAME_FIRST,
                value="Jane",
                start=11,
                end=15,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.NAME_LAST,
                value="Doe",
                start=16,
                end=19,
                confidence=0.95
            )
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Sincerely, Jane Doe"
        redacted, state = loop.redact(original)
        
        assert redacted == "Sincerely, [NAME_FIRST_1] [NAME_LAST_1]"
        
        # LLM processes and creates personalized greeting
        llm_response = "Dear [NAME_FIRST_1],\n\nThank you for reaching out..."
        
        unredacted, issues = loop.unredact(llm_response, state)
        assert unredacted == "Dear Jane,\n\nThank you for reaching out..."
        assert len(issues) == 0
    
    def test_customer_support_conversation(self):
        """Test multi-turn customer support conversation."""
        # Simulate a customer support chat
        detector = MockDetector([])  # Will update for each turn
        loop = PIILoop(detector=detector)
        
        with PIISession(loop) as session:
            # Turn 1: Customer provides contact info
            loop._detector = MockDetector([
                PIIEntity(PIIType.PERSON, "Sarah Johnson", 22, 35, 0.95),
                PIIEntity(PIIType.EMAIL, "sarah.j@example.com", 40, 58, 0.98),
                PIIEntity(PIIType.PHONE, "555-123-4567", 68, 80, 0.99)
            ])
            
            customer_msg1 = "Hi, my name is Sarah Johnson and sarah.j@example.com phone is 555-123-4567"
            redacted1 = session.redact(customer_msg1)
            assert "[PERSON_1]" in redacted1
            assert "[EMAIL_1]" in redacted1
            assert "[PHONE_1]" in redacted1
            
            # LLM processes and responds
            agent_response1 = "Hello [PERSON_1]! I see your email is [EMAIL_1]. How can I help?"
            unredacted1, issues1 = session.unredact(agent_response1)
            assert "Sarah Johnson" in unredacted1
            assert "sarah.j@example.com" in unredacted1
            assert len(issues1) == 0
            
            # Turn 2: Customer mentions credit card
            loop._detector = MockDetector([
                PIIEntity(PIIType.CREDIT_CARD, "4111-1111-1111-1234", 37, 56, 0.99)
            ])
            
            customer_msg2 = "I have an issue with my credit card 4111-1111-1111-1234"
            redacted2 = session.redact(customer_msg2)
            assert "[CREDIT_CARD_1]" in redacted2
            
            # Turn 3: Agent summarizes (all tokens should work)
            agent_summary = ("I'll help you with [CREDIT_CARD_1]. I'll send confirmation to "
                           "[EMAIL_1] and call [PHONE_1] if needed.")
            unredacted_summary, issues = session.unredact(agent_summary)
            
            assert "4111-1111-1111-1234" in unredacted_summary
            assert "sarah.j@example.com" in unredacted_summary
            assert "555-123-4567" in unredacted_summary
            assert len(issues) == 0
    
    def test_llm_hallucination_recovery(self):
        """Test handling of LLM hallucinations in production scenario."""
        entities = [
            PIIEntity(PIIType.PERSON, "Robert Smith", 0, 12, 0.95),
            PIIEntity(PIIType.EMAIL, "rsmith@corp.com", 25, 40, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Robert Smith works at rsmith@corp.com"
        redacted, state = loop.redact(original)
        
        # LLM hallucinates additional entities
        llm_response = ("[PERSON_1] ([PERSON_2]) can be reached at [EMAIL_1] "
                       "or backup email [EMAIL_2], phone [PHONE_1]")
        
        # Default mode - exact matches only
        unredacted, issues = loop.unredact(llm_response, state)
        
        # Should replace real tokens and detect hallucinations
        assert "Robert Smith" in unredacted
        assert "rsmith@corp.com" in unredacted
        assert "[PERSON_2]" in unredacted
        assert "[EMAIL_2]" in unredacted
        assert "[PHONE_1]" in unredacted
        
        # Should have 3 hallucination issues
        assert len(issues) == 3
        hallucinated_tokens = {issue.token for issue in issues}
        assert hallucinated_tokens == {"[PERSON_2]", "[EMAIL_2]", "[PHONE_1]"}
    
    def test_fuzzy_matching_real_scenario(self):
        """Test fuzzy matching with common LLM errors."""
        entities = [
            PIIEntity(PIIType.EMAIL, "jennifer@company.com", 6, 26, 0.95),
            PIIEntity(PIIType.PHONE, "555-9876", 36, 44, 0.90)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Email jennifer@company.com or call 555-9876"
        redacted, state = loop.redact(original)
        
        # LLM makes common mistakes
        llm_with_typos = "Contact [EMIAL_1] or [email_1] by phone [PHOEN_1]"
        
        # Without fuzzy matching
        unredacted_strict, issues_strict = loop.unredact(llm_with_typos, state)
        assert "jennifer@company.com" not in unredacted_strict
        assert len(issues_strict) == 3  # All are hallucinations
        
        # With fuzzy matching
        unredacted_fuzzy, issues_fuzzy = loop.unredact(llm_with_typos, state, fuzzy=True)
        assert unredacted_fuzzy == "Contact jennifer@company.com or jennifer@company.com by phone 555-9876"
        assert len(issues_fuzzy) == 3
        assert all(issue.issue_type == "fuzzy_match" for issue in issues_fuzzy)
    
    def test_state_persistence_across_sessions(self):
        """Test saving and restoring state across application restarts."""
        # First session - collect PII
        entities = [
            PIIEntity(PIIType.PERSON, "Alice Cooper", 0, 12, 0.95),
            PIIEntity(PIIType.SSN, "123-45-6789", 18, 29, 0.99)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        
        # Simulate first application session
        with PIISession(loop) as session1:
            msg = "Alice Cooper SSN: 123-45-6789"
            redacted = session1.redact(msg)
            state_to_save = session1.get_state()
            
            # Serialize state (simulating save to database)
            serialized_state = state_to_save.to_json()
        
        # Simulate application restart - restore state
        restored_state = RedactionState.from_json(serialized_state)
        
        # Second session with restored state
        with PIISession(loop, initial_state=restored_state) as session2:
            # LLM response using previous tokens
            llm_response = "I've verified [PERSON_1]'s SSN [SSN_1]"
            unredacted, issues = session2.unredact(llm_response)
            
            assert unredacted == "I've verified Alice Cooper's SSN 123-45-6789"
            assert len(issues) == 0
    
    def test_mixed_language_pii(self):
        """Test handling PII in mixed language content."""
        # Build text and calculate correct positions
        original = "Contact José García and 李明 at jose@empresa.es"
        
        # Find actual positions
        jose_start = original.find("José García")
        jose_end = jose_start + len("José García")
        li_start = original.find("李明")
        li_end = li_start + len("李明")
        email_start = original.find("jose@empresa.es")
        email_end = email_start + len("jose@empresa.es")
        
        entities = [
            PIIEntity(PIIType.PERSON, "José García", jose_start, jose_end, 0.95),
            PIIEntity(PIIType.PERSON, "李明", li_start, li_end, 0.90),
            PIIEntity(PIIType.EMAIL, "jose@empresa.es", email_start, email_end, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        redacted, state = loop.redact(original)
        
        assert "[PERSON_1]" in redacted
        assert "[PERSON_2]" in redacted
        assert "[EMAIL_1]" in redacted
        assert "José García" not in redacted
        assert "李明" not in redacted
        assert "jose@empresa.es" not in redacted
        
        # LLM response maintains order
        llm_response = "I'll email [EMAIL_1] to reach [PERSON_1] and [PERSON_2]"
        unredacted, issues = loop.unredact(llm_response, state)
        
        assert "José García" in unredacted
        assert "李明" in unredacted
        assert "jose@empresa.es" in unredacted
        assert len(issues) == 0
    
    def test_complex_document_processing(self):
        """Test processing a complex document with many PII entities."""
        document = """From: John Smith <jsmith@acme.com> 555-0123
        
Client: Mary Johnson
Credit Card: 4532-1234-5678-9012
SSN: 987-65-4321
Contact: mary.j@client.com Phone: 555-9999"""
        
        # Calculate actual positions in the document
        john_start = document.find("John Smith")
        john_end = john_start + len("John Smith")
        
        jsmith_start = document.find("jsmith@acme.com")
        jsmith_end = jsmith_start + len("jsmith@acme.com")
        
        phone1_start = document.find("555-0123")
        phone1_end = phone1_start + len("555-0123")
        
        mary_start = document.find("Mary Johnson")
        mary_end = mary_start + len("Mary Johnson")
        
        cc_start = document.find("4532-1234-5678-9012")
        cc_end = cc_start + len("4532-1234-5678-9012")
        
        ssn_start = document.find("987-65-4321")
        ssn_end = ssn_start + len("987-65-4321")
        
        mary_email_start = document.find("mary.j@client.com")
        mary_email_end = mary_email_start + len("mary.j@client.com")
        
        phone2_start = document.find("555-9999")
        phone2_end = phone2_start + len("555-9999")
        
        entities = [
            PIIEntity(PIIType.PERSON, "John Smith", john_start, john_end, 0.95),
            PIIEntity(PIIType.EMAIL, "jsmith@acme.com", jsmith_start, jsmith_end, 0.98),
            PIIEntity(PIIType.PHONE, "555-0123", phone1_start, phone1_end, 0.95),
            PIIEntity(PIIType.PERSON, "Mary Johnson", mary_start, mary_end, 0.95),
            PIIEntity(PIIType.CREDIT_CARD, "4532-1234-5678-9012", cc_start, cc_end, 0.99),
            PIIEntity(PIIType.SSN, "987-65-4321", ssn_start, ssn_end, 0.99),
            PIIEntity(PIIType.EMAIL, "mary.j@client.com", mary_email_start, mary_email_end, 0.95),
            PIIEntity(PIIType.PHONE, "555-9999", phone2_start, phone2_end, 0.90)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        redacted, state = loop.redact(document)
        
        # Verify all PII is redacted
        assert "John Smith" not in redacted
        assert "jsmith@acme.com" not in redacted
        assert "555-0123" not in redacted
        assert "Mary Johnson" not in redacted
        assert "4532-1234-5678-9012" not in redacted
        assert "987-65-4321" not in redacted
        assert "mary.j@client.com" not in redacted
        assert "555-9999" not in redacted
        
        # Verify tokens are present
        assert "[PERSON_1]" in redacted
        assert "[EMAIL_1]" in redacted
        assert "[PHONE_1]" in redacted
        assert "[PERSON_2]" in redacted
        assert "[CREDIT_CARD_1]" in redacted
        assert "[SSN_1]" in redacted
        assert "[EMAIL_2]" in redacted
        assert "[PHONE_2]" in redacted
        
        # Process through LLM and unredact
        processed = redacted  # Simulate LLM returning same tokens
        unredacted, issues = loop.unredact(processed, state)
        
        assert unredacted == document
        assert len(issues) == 0
    
    def test_error_handling_graceful_degradation(self):
        """Test system handles errors gracefully without leaking PII."""
        entities = [
            PIIEntity(PIIType.EMAIL, "sensitive@data.com", 14, 32, 0.95)
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Do not leak: sensitive@data.com"
        redacted, state = loop.redact(original)
        
        # Simulate various error scenarios
        
        # 1. Corrupted token format
        corrupted = "Email is EMAIL_1] (missing bracket)"
        unredacted, issues = loop.unredact(corrupted, state)
        assert "sensitive@data.com" not in unredacted  # No PII leak
        
        # 2. Empty response
        empty_response = ""
        unredacted, issues = loop.unredact(empty_response, state)
        assert unredacted == ""
        
        # 3. None/null handling - unredact expects string
        # Test with empty string instead
        empty_unredacted, _ = loop.unredact("", state)
        assert empty_unredacted == ""
    
    def test_high_volume_token_handling(self):
        """Test handling many tokens efficiently."""
        # Build text with proper spacing
        original_parts = []
        entities = []
        current_pos = 0
        
        for i in range(50):
            email = f"user{i}@example.com"
            if i > 0:
                original_parts.append(" ")
                current_pos += 1
            
            original_parts.append(email)
            entities.append(
                PIIEntity(PIIType.EMAIL, email, current_pos, current_pos + len(email), 0.95)
            )
            current_pos += len(email)
        
        original = "".join(original_parts)
        loop = PIILoop(detector=MockDetector(entities))
        
        # Redact
        redacted, state = loop.redact(original)
        
        # Should have EMAIL_1 through EMAIL_50
        for i in range(1, 51):
            assert f"[EMAIL_{i}]" in redacted
        
        # Should not have any email addresses
        for i in range(50):
            assert f"user{i}@example.com" not in redacted
        
        # Unredact should restore all
        unredacted, issues = loop.unredact(redacted, state)
        assert unredacted == original
        assert len(issues) == 0