"""Tests for hallucination detection and handling."""

import pytest
from redactyl import PIIEntity, PIIType, RedactionState, RedactionToken
from redactyl.core import PIILoop
from redactyl.detectors.mock import MockDetector
from redactyl.handlers import DefaultHallucinationHandler, HallucinationHandler


class TestHallucinationDetection:
    """Test detection of LLM-generated tokens."""
    
    def test_detect_simple_hallucination(self):
        """Test detecting a completely hallucinated token."""
        # Set up initial redaction
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="real@example.com",
            start=5,
            end=21,
            confidence=0.95
        )
        
        loop = PIILoop(detector=MockDetector([entity]))
        original = "Send real@example.com the docs"
        redacted, state = loop.redact(original)
        
        # LLM response with hallucinated token
        llm_response = "I'll email [EMAIL_1] and CC [EMAIL_2]"
        
        unredacted, issues = loop.unredact(llm_response, state)
        
        # Default mode: should detect [EMAIL_2] as hallucination (no fuzzy matching)
        assert len(issues) == 1
        assert issues[0].token == "[EMAIL_2]"
        assert issues[0].issue_type == "hallucination"
        assert issues[0].replacement is None
        assert "[EMAIL_2]" in unredacted  # Token preserved in output
    
    def test_multiple_hallucinations(self):
        """Test detecting multiple hallucinated tokens."""
        loop = PIILoop(detector=MockDetector([]))
        _, state = loop.redact("No PII here")
        
        # LLM generates multiple tokens
        llm_response = "Contact [PERSON_1] at [EMAIL_1] or [PHONE_1]"
        
        unredacted, issues = loop.unredact(llm_response, state)
        
        # All tokens are hallucinations
        assert len(issues) == 3
        token_set = {issue.token for issue in issues}
        assert token_set == {"[PERSON_1]", "[EMAIL_1]", "[PHONE_1]"}
        
        # All tokens preserved
        assert "[PERSON_1]" in unredacted
        assert "[EMAIL_1]" in unredacted
        assert "[PHONE_1]" in unredacted
    
    def test_mixed_real_and_hallucinated(self):
        """Test mix of real and hallucinated tokens."""
        entities = [
            PIIEntity(
                type=PIIType.PERSON,
                value="Alice",
                start=0,
                end=5,
                confidence=0.95
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="alice@example.com",
                start=14,
                end=31,
                confidence=0.95
            )
        ]
        
        loop = PIILoop(detector=MockDetector(entities))
        original = "Alice's email: alice@example.com"
        redacted, state = loop.redact(original)
        
        # LLM adds extra tokens
        llm_response = "[PERSON_1] ([PERSON_2]) can be reached at [EMAIL_1] or [EMAIL_2]"
        
        unredacted, issues = loop.unredact(llm_response, state)
        
        # Should detect 2 hallucinations
        assert len(issues) == 2
        hallucinated = {issue.token for issue in issues}
        assert hallucinated == {"[PERSON_2]", "[EMAIL_2]"}
        
        # Real tokens replaced
        assert "Alice" in unredacted
        assert "alice@example.com" in unredacted
        
        # Check that hallucinated tokens are either preserved or replaced
        # (depending on whether fuzzy matching found something)
        # [PERSON_2] and [EMAIL_2] should be hallucinations since 
        # they have different indices than existing tokens


class TestDefaultHallucinationHandler:
    """Test the default hallucination handler."""
    
    @pytest.fixture
    def handler(self):
        """Create a default handler."""
        return DefaultHallucinationHandler()
    
    @pytest.fixture
    def sample_state(self):
        """Create a sample state with tokens."""
        entity1 = PIIEntity(
            type=PIIType.EMAIL,
            value="test@example.com",
            start=0,
            end=16,
            confidence=0.95
        )
        token1 = RedactionToken(
            original="test@example.com",
            pii_type=PIIType.EMAIL,
            token_index=1,
            entity=entity1
        )
        
        entity2 = PIIEntity(
            type=PIIType.PERSON,
            value="John Doe",
            start=20,
            end=28,
            confidence=0.90
        )
        token2 = RedactionToken(
            original="John Doe",
            pii_type=PIIType.PERSON,
            token_index=1,
            entity=entity2
        )
        
        return RedactionState(
            tokens={
                "[EMAIL_1]": token1,
                "[PERSON_1]": token2
            }
        )
    
    def test_handle_exact_hallucination(self, handler, sample_state):
        """Test handling a completely unknown token."""
        issue = handler.handle("[PHONE_1]", sample_state, strict=False)
        
        assert issue is not None
        assert issue.token == "[PHONE_1]"
        assert issue.issue_type == "hallucination"
        assert issue.replacement is None
        assert issue.confidence == 0.0
    
    def test_handle_fuzzy_match_typo(self, handler, sample_state):
        """Test fuzzy matching for typos."""
        # Simulate typo in token
        issue = handler.handle("[EMIAL_1]", sample_state, strict=False)
        
        assert issue is not None
        assert issue.token == "[EMIAL_1]"
        assert issue.issue_type == "fuzzy_match"
        assert issue.replacement == "test@example.com"
        assert issue.confidence > 0.8
    
    def test_handle_case_variation(self, handler, sample_state):
        """Test handling case variations."""
        issue = handler.handle("[email_1]", sample_state, strict=False)
        
        assert issue is not None
        assert issue.issue_type == "fuzzy_match"
        assert issue.replacement == "test@example.com"
        assert issue.confidence > 0.9
    
    def test_handle_strict_mode(self, handler, sample_state):
        """Test strict mode rejects fuzzy matches."""
        # In strict mode, even close matches are treated as hallucinations
        issue = handler.handle("[EMIAL_1]", sample_state, strict=True)
        
        assert issue is not None
        assert issue.issue_type == "hallucination"  # Not fuzzy_match
        assert issue.replacement is None
    
    def test_handle_valid_token(self, handler, sample_state):
        """Test that valid tokens return no issue."""
        issue = handler.handle("[EMAIL_1]", sample_state, strict=False)
        
        assert issue is None  # Valid token, no issue
    
    def test_similarity_threshold(self, handler, sample_state):
        """Test similarity threshold for fuzzy matching."""
        # Very different token shouldn't fuzzy match
        issue = handler.handle("[SOMETHING_1]", sample_state, strict=False)
        
        assert issue is not None
        assert issue.issue_type == "hallucination"  # Too different for fuzzy match
        assert issue.replacement is None