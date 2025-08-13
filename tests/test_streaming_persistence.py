"""Tests for streaming with persistent token numbering."""

import pytest
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig
from redactyl.types import PIIEntity, PIIType


class User(BaseModel):
    """Test model for streaming."""
    name: str
    email: str


class FakeDetector:
    """Fake detector that finds specific names."""
    
    def detect(self, text: str) -> list[PIIEntity]:
        """Detect John Doe and John as person entities."""
        res: list[PIIEntity] = []
        for needle in ["John Doe", "John"]:
            start = text.find(needle)
            if start != -1:
                res.append(PIIEntity(PIIType.PERSON, needle, start, start + len(needle), 0.9))
        return res


@pytest.mark.asyncio
async def test_streaming_persistent_name_indices_async():
    """Test that name indices persist across async yields."""
    detector = FakeDetector()
    config = PIIConfig(detector=detector, batch_detection=False, use_name_parsing=False)

    @config.protect
    async def gen():
        yield User(name="John Doe", email="a@b.com")
        yield User(name="John", email="c@d.com")

    out = []
    async for item in gen():
        out.append(item)

    # Both should have [PERSON_1] since "John" is a component of "John Doe"
    assert "[PERSON_1]" in out[0].name
    assert "[PERSON_1]" in out[1].name


def test_streaming_persistent_name_indices_sync():
    """Test that name indices persist across sync yields."""
    detector = FakeDetector()
    config = PIIConfig(detector=detector, batch_detection=False, use_name_parsing=False)

    @config.protect
    def gen():
        yield User(name="John Doe", email="a@b.com")
        yield User(name="John", email="c@d.com")

    out = list(gen())
    
    # Both should have [PERSON_1] since "John" is a component of "John Doe"
    assert "[PERSON_1]" in out[0].name
    assert "[PERSON_1]" in out[1].name


def test_streaming_persistent_email_indices():
    """Test that non-name entities also get persistent indices."""
    
    class EmailDetector:
        """Detector for emails."""
        
        def detect(self, text: str) -> list[PIIEntity]:
            """Detect email patterns."""
            res: list[PIIEntity] = []
            import re
            for match in re.finditer(r'\b[a-z]+@[a-z]+\.com\b', text):
                res.append(PIIEntity(
                    PIIType.EMAIL, 
                    match.group(),
                    match.start(),
                    match.end(),
                    0.95
                ))
            return res
    
    detector = EmailDetector()
    config = PIIConfig(detector=detector, batch_detection=True)
    
    @config.protect
    def gen():
        yield User(name="Alice", email="alice@example.com")
        yield User(name="Bob", email="bob@example.com")  
        yield User(name="Charlie", email="alice@example.com")  # Repeated email
    
    out = list(gen())
    
    # Streaming yields protected (redacted) models
    print(f"Email 1: {out[0].email}")  
    print(f"Email 2: {out[1].email}")
    print(f"Email 3: {out[2].email}")
    
    # First email gets [EMAIL_1]
    assert "[EMAIL_1]" in out[0].email
    # Second unique email gets [EMAIL_2]
    assert "[EMAIL_2]" in out[1].email
    # Third is same as first, should reuse [EMAIL_1]
    assert "[EMAIL_1]" in out[2].email