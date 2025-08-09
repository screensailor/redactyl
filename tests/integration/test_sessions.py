"""Tests for PIISession management."""

import pytest
from redactyl import PIIEntity, PIILoop, PIIType
from redactyl.detectors.mock import MockDetector
from redactyl.session import PIISession


class TestPIISession:
    """Test session management for multi-turn conversations."""
    
    def test_session_context_manager(self):
        """Test session works as context manager."""
        loop = PIILoop(detector=MockDetector([]))
        
        with PIISession(loop) as session:
            assert session is not None
            assert hasattr(session, 'redact')
            assert hasattr(session, 'unredact')
    
    def test_session_accumulates_state(self):
        """Test that session accumulates state across turns."""
        # First turn entities
        entities1 = [
            PIIEntity(
                type=PIIType.EMAIL,
                value="alice@example.com",
                start=18,
                end=35,
                confidence=0.95
            )
        ]
        
        # Second turn entities
        entities2 = [
            PIIEntity(
                type=PIIType.PHONE,
                value="555-1234",
                start=12,
                end=20,
                confidence=0.90
            )
        ]
        
        # Third turn entities (another email)
        entities3 = [
            PIIEntity(
                type=PIIType.EMAIL,
                value="bob@example.com",
                start=6,
                end=21,
                confidence=0.95
            )
        ]
        
        # Create loop with changing detector
        detector = MockDetector(entities1)
        loop = PIILoop(detector=detector)
        
        with PIISession(loop) as session:
            # Turn 1
            text1 = "Please contact me alice@example.com"
            redacted1 = session.redact(text1)
            assert redacted1 == "Please contact me [EMAIL_1]"
            
            # Change detector for turn 2
            loop._detector = MockDetector(entities2)
            
            # Turn 2 
            text2 = "My phone is 555-1234"
            redacted2 = session.redact(text2)
            assert redacted2 == "My phone is [PHONE_1]"
            
            # Change detector for turn 3
            loop._detector = MockDetector(entities3)
            
            # Turn 3 - should use [EMAIL_2] not [EMAIL_1]
            text3 = "Email bob@example.com too"
            redacted3 = session.redact(text3)
            assert redacted3 == "Email [EMAIL_2] too"
            
            # Test unredaction with accumulated state
            response = "I'll email [EMAIL_1], [EMAIL_2], and call [PHONE_1]"
            unredacted, issues = session.unredact(response)
            
            assert unredacted == "I'll email alice@example.com, bob@example.com, and call 555-1234"
            assert len(issues) == 0
    
    def test_session_handles_hallucinations(self):
        """Test session handles hallucinated tokens across turns."""
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="Alice",
            start=0,
            end=5,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        
        with PIISession(loop) as session:
            # Redact
            redacted = session.redact("Alice is here")
            assert redacted == "[PERSON_1] is here"
            
            # LLM response with hallucination
            response = "[PERSON_1] and [PERSON_2] are working together"
            unredacted, issues = session.unredact(response)
            
            assert "Alice" in unredacted
            assert "[PERSON_2]" in unredacted
            assert len(issues) == 1
            assert issues[0].token == "[PERSON_2]"
    
    def test_session_token_numbering(self):
        """Test that token numbering continues across turns."""
        # Multiple people across turns
        entities1 = [
            PIIEntity(
                type=PIIType.PERSON,
                value="Alice",
                start=0,
                end=5,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.PERSON,
                value="Bob",
                start=10,
                end=13,
                confidence=0.95
            )
        ]
        
        entities2 = [
            PIIEntity(
                type=PIIType.PERSON,
                value="Charlie",
                start=0,
                end=7,
                confidence=0.95
            )
        ]
        
        detector = MockDetector(entities1)
        loop = PIILoop(detector=detector)
        
        with PIISession(loop) as session:
            # Turn 1 - should get PERSON_1 and PERSON_2
            text1 = "Alice and Bob are here"
            redacted1 = session.redact(text1)
            assert "[PERSON_1]" in redacted1
            assert "[PERSON_2]" in redacted1
            
            # Turn 2 - should get PERSON_3
            loop._detector = MockDetector(entities2)
            text2 = "Charlie joined"
            redacted2 = session.redact(text2)
            assert "[PERSON_3]" in redacted2
            assert "[PERSON_1]" not in redacted2
    
    def test_session_state_isolation(self):
        """Test that different sessions have isolated state."""
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        
        # First session
        with PIISession(loop) as session1:
            redacted1 = session1.redact("test@example.com")
            assert redacted1 == "[EMAIL_1]"
        
        # Second session - should restart numbering
        with PIISession(loop) as session2:
            redacted2 = session2.redact("test@example.com")
            assert redacted2 == "[EMAIL_1]"  # Not [EMAIL_2]
    
    def test_session_get_state(self):
        """Test retrieving accumulated state from session."""
        entities = [
            PIIEntity(
                type=PIIType.CREDIT_CARD,
                value="4111-1111-1111-1111",
                start=4,
                end=23,
                confidence=0.99
            )
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        
        with PIISession(loop) as session:
            session.redact("CC: 4111-1111-1111-1111")
            
            # Get current state
            state = session.get_state()
            assert "[CREDIT_CARD_1]" in state.tokens
            assert state.tokens["[CREDIT_CARD_1]"].original == "4111-1111-1111-1111"
    
    def test_session_with_initial_state(self):
        """Test starting session with pre-existing state."""
        # Create initial state from previous session
        entity = PIIEntity(
            type=PIIType.PERSON,
            value="Previous User",
            start=0,
            end=13,
            confidence=0.90
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        _, initial_state = loop.redact("Previous User")
        
        # Start new session with that state
        new_entity = PIIEntity(
            type=PIIType.PERSON,
            value="New User",
            start=0,
            end=8,
            confidence=0.90
        )
        
        loop._detector = MockDetector([new_entity])
        
        with PIISession(loop, initial_state=initial_state) as session:
            # Should continue numbering from previous state
            redacted = session.redact("New User")
            assert redacted == "[PERSON_2]"  # Not [PERSON_1]
            
            # Can still unredact old tokens
            unredacted, _ = session.unredact("[PERSON_1] and [PERSON_2]")
            assert unredacted == "Previous User and New User"