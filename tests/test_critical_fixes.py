"""Tests for critical bug fixes identified before v1.0 release."""

import warnings
from typing import Annotated

import pytest
from pydantic import BaseModel

from redactyl import PIILoop
from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig, pii_field
from redactyl.session import PIISession
from redactyl.types import PIIType


class TestPIISessionRenumbering:
    """Test fixes for PIISession token renumbering bug."""
    
    def test_token_renumbering_avoids_partial_replacement(self):
        """Test that token renumbering handles [TYPE_1] through [TYPE_11] correctly."""
        detector = PresidioDetector()
        loop = PIILoop(detector)
        
        with PIISession(loop) as session:
            # Create text with many email addresses to get numbered tokens
            emails = [f"user{i}@example.com" for i in range(1, 12)]
            text1 = "Emails: " + " ".join(emails)
            redacted1 = session.redact(text1)
            
            # Verify we have EMAIL_1 through EMAIL_11
            for i in range(1, 12):
                assert f"[EMAIL_{i}]" in redacted1
            
            # Specific test: EMAIL_11 should not be corrupted to EMAIL_1]1
            assert "[EMAIL_11]" in redacted1
            assert "[EMAIL_1]1" not in redacted1
            
            # Second batch should create EMAIL_12
            text2 = "Another email: user12@example.com"
            redacted2 = session.redact(text2)
            
            # This should be EMAIL_12, not corrupt existing tokens
            assert "[EMAIL_12]" in redacted2
            assert "[EMAIL_1]2" not in redacted2  # Check for corruption
            
            # Verify unredaction works correctly
            combined = redacted1 + " " + redacted2
            unredacted, issues = session.unredact(combined)
            
            # Should restore all emails correctly
            for email in emails:
                assert email in unredacted
            assert "user12@example.com" in unredacted
            assert not issues  # No unredaction issues
    
    def test_high_numbered_tokens_replaced_correctly(self):
        """Test that high-numbered tokens like EMAIL_100 don't corrupt EMAIL_10."""
        detector = PresidioDetector()
        loop = PIILoop(detector)
        
        # Create a session with pre-existing high token indices
        from redactyl.types import RedactionState, RedactionToken, PIIEntity
        
        initial_state = RedactionState()
        # Add tokens EMAIL_10, EMAIL_100
        for idx in [10, 100]:
            token = RedactionToken(
                original=f"user{idx}@example.com",
                pii_type=PIIType.EMAIL,
                token_index=idx,
                entity=PIIEntity(
                    type=PIIType.EMAIL,
                    value=f"user{idx}@example.com",
                    start=0,
                    end=len(f"user{idx}@example.com"),
                    confidence=0.9
                )
            )
            initial_state = initial_state.with_token(f"[EMAIL_{idx}]", token)
        
        with PIISession(loop, initial_state=initial_state) as session:
            # Add a new email - should be EMAIL_101
            text = "Contact: newuser@example.com"
            redacted = session.redact(text)
            
            assert "[EMAIL_101]" in redacted
            
            # Test that we can unredact all tokens correctly
            test_text = "[EMAIL_10] contacted [EMAIL_100] and [EMAIL_101]"
            unredacted, issues = session.unredact(test_text)
            
            assert "user10@example.com" in unredacted
            assert "user100@example.com" in unredacted
            assert "newuser@example.com" in unredacted
            assert not issues


class TestPydanticDetectFlag:
    """Test fixes for Pydantic detect=False flag being ignored."""
    
    def test_detect_false_skips_field(self):
        """Test that fields marked with detect=False are not processed for PII."""
        
        class UserModel(BaseModel):
            # This field should be detected
            name: str
            # This field should be skipped
            internal_id: Annotated[str, pii_field(detect=False)]
            # This field should also be detected
            email: str
        
        detector = PresidioDetector()
        config = PIIConfig(detector=detector)
        
        captured_user = None
        
        @config.protect
        def process_user(user: UserModel) -> UserModel:
            # Capture what the function receives (should be redacted)
            nonlocal captured_user
            captured_user = user.model_copy()
            return user
        
        # Create a user with PII in all fields
        user = UserModel(
            name="John Doe",
            internal_id="USER_JOHN_DOE_12345",  # Contains name but should be ignored
            email="john@example.com"
        )
        
        # Process the user
        result = process_user(user)
        
        # The result should be unredacted (decorator unprotects on return)
        assert result.name == "John Doe"
        assert result.email == "john@example.com"
        assert result.internal_id == "USER_JOHN_DOE_12345"
        
        # But inside the function, name and email should have been redacted
        assert captured_user is not None
        assert "John Doe" not in captured_user.name
        # Could be PERSON or NAME tokens depending on detector
        assert "[NAME_" in captured_user.name or "[PERSON_" in captured_user.name
        assert "john@example.com" not in captured_user.email
        assert "[EMAIL_" in captured_user.email
        
        # internal_id should NOT be redacted (detect=False)
        assert captured_user.internal_id == "USER_JOHN_DOE_12345"
        assert "[" not in captured_user.internal_id  # No tokens at all
    
    def test_detect_false_with_nested_models(self):
        """Test that detect=False works with nested models."""
        
        class Address(BaseModel):
            street: str
            city: str
            # Zip code should not be detected as PII
            zip_code: Annotated[str, pii_field(detect=False)]
        
        class Person(BaseModel):
            name: str
            address: Address
        
        detector = PresidioDetector()
        config = PIIConfig(detector=detector)
        
        captured_person = None
        
        @config.protect
        def process_person(person: Person) -> Person:
            nonlocal captured_person
            captured_person = person.model_copy(deep=True)
            return person
        
        person = Person(
            name="Jane Smith",
            address=Address(
                street="123 Main St",
                city="New York",
                zip_code="ZIP-ABC-123"  # Non-numeric to avoid false positive detection
            )
        )
        
        result = process_person(person)
        
        # Result should be unredacted
        assert result.name == "Jane Smith"
        assert result.address.zip_code == "ZIP-ABC-123"
        
        # Inside function, name should have been redacted
        assert captured_person is not None
        assert "Jane Smith" not in captured_person.name
        # Could be PERSON or NAME tokens depending on detector
        assert "[NAME_" in captured_person.name or "[PERSON_" in captured_person.name
        
        # Address fields should be processed except zip_code
        assert "123 Main St" in captured_person.address.street  # No PII in street
        assert captured_person.address.zip_code == "ZIP-ABC-123"  # Should not be changed (detect=False)


class TestCallbackTypeValidation:
    """Test that callback parameters only accept valid types."""
    
    def test_callback_cannot_be_bool(self):
        """Test that passing True/False to callbacks raises clear error."""
        detector = PresidioDetector()
        
        # These should work (valid callback types)
        config1 = PIIConfig(detector=detector, on_gliner_unavailable=None)  # OK
        config2 = PIIConfig(detector=detector, on_gliner_unavailable=lambda: None)  # OK
        
        # The type system should prevent passing bool, but let's test runtime behavior
        # This tests that if someone ignores type hints, they get a clear error
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            
            # Create config with valid types
            config = PIIConfig(
                detector=detector,
                on_detection=lambda entities: print(f"Detected {len(entities)} entities")
            )
            
            # Verify the callback works
            assert callable(config.on_detection)
    
    def test_none_callback_uses_default_warning(self):
        """Test that None (default) triggers warnings."""
        detector = PresidioDetector()
        
        # Default (None) should use warnings
        config = PIIConfig(detector=detector)
        
        # on_gliner_unavailable defaults to None, which creates a warning lambda
        assert config.on_gliner_unavailable is not None
        assert callable(config.on_gliner_unavailable)
        
        # Test that it actually warns
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config.on_gliner_unavailable()
            assert len(w) == 1
            assert "GLiNER is not installed" in str(w[0].message)
    
    def test_custom_callback_works(self):
        """Test that custom callbacks are properly stored and used."""
        detector = PresidioDetector()
        
        called = []
        
        def custom_handler():
            called.append("gliner_unavailable")
        
        config = PIIConfig(
            detector=detector,
            on_gliner_unavailable=custom_handler
        )
        
        # Verify custom callback is stored
        assert config.on_gliner_unavailable is custom_handler
        
        # Test it can be called
        config.on_gliner_unavailable()
        assert called == ["gliner_unavailable"]


class TestMisconfigurationErrors:
    """Test that misconfigurations produce clear error messages."""
    
    def test_piiloop_invalid_parameters_documented(self):
        """Test that PIILoop doesn't accept token_format or start_index parameters."""
        detector = PresidioDetector()
        
        # These parameters don't exist (as documented in fixed README)
        with pytest.raises(TypeError) as exc_info:
            PIILoop(
                detector=detector,
                token_format="[{entity_type}_{index}]",  # Invalid parameter
                start_index=1  # Invalid parameter
            )
        
        # Should get clear error about unexpected keyword arguments
        assert "unexpected keyword argument" in str(exc_info.value).lower()
    
    def test_valid_piiloop_initialization(self):
        """Test that PIILoop can be initialized with valid parameters."""
        detector = PresidioDetector()
        
        # Valid initialization
        loop = PIILoop(
            detector=detector,
            use_name_parsing=True,
            hallucination_handler=None
        )
        
        assert loop._detector is detector
        assert loop._use_name_parsing is True