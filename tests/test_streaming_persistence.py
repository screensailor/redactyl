"""Tests for streaming with persistent token numbering."""

from typing import Optional

import pytest
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig
from redactyl.types import PIIEntity, PIIType, RedactionState


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
    """Async generator yields unredacted values; state persists indices."""
    detector = FakeDetector()
    captured_state: Optional[RedactionState] = None

    def on_complete(state: RedactionState) -> None:
        nonlocal captured_state
        captured_state = state

    config = PIIConfig(
        detector=detector,
        batch_detection=False,
        use_name_parsing=False,
        on_stream_complete=on_complete,
    )

    @config.protect
    async def gen():
        yield User(name="John Doe", email="a@b.com")
        yield User(name="John", email="c@d.com")

    out = []
    async for item in gen():
        out.append(item)

    # Outside the bubble, values are unredacted
    assert out[0].name == "John Doe"
    assert out[1].name == "John"

    # Accumulated state has persistent token indices
    assert captured_state is not None
    person_tokens = [t for t in captured_state.tokens if t.startswith("[PERSON_")]
    assert set(person_tokens) == {"[PERSON_1]"}


def test_streaming_persistent_name_indices_sync():
    """Sync generator yields unredacted values; state persists indices."""
    detector = FakeDetector()
    captured_state: Optional[RedactionState] = None

    def on_complete(state: RedactionState) -> None:
        nonlocal captured_state
        captured_state = state

    config = PIIConfig(
        detector=detector,
        batch_detection=False,
        use_name_parsing=False,
        on_stream_complete=on_complete,
    )

    @config.protect
    def gen():
        yield User(name="John Doe", email="a@b.com")
        yield User(name="John", email="c@d.com")

    out = list(gen())

    # Outside the bubble, values are unredacted
    assert out[0].name == "John Doe"
    assert out[1].name == "John"

    # Accumulated state has persistent token indices
    assert captured_state is not None
    person_tokens = [t for t in captured_state.tokens if t.startswith("[PERSON_")]
    assert set(person_tokens) == {"[PERSON_1]"}


def test_streaming_persistent_email_indices():
    """Non-name entities get persistent indices via accumulated state."""
    
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
    captured_state: Optional[RedactionState] = None

    def on_complete(state: RedactionState) -> None:
        nonlocal captured_state
        captured_state = state

    config = PIIConfig(detector=detector, batch_detection=True, on_stream_complete=on_complete)
    
    @config.protect
    def gen():
        yield User(name="Alice", email="alice@example.com")
        yield User(name="Bob", email="bob@example.com")  
        yield User(name="Charlie", email="alice@example.com")  # Repeated email
    
    out = list(gen())

    # Outside the bubble, values are unredacted
    assert out[0].email == "alice@example.com"
    assert out[1].email == "bob@example.com"
    assert out[2].email == "alice@example.com"

    # Accumulated state shows two unique EMAIL tokens with stable indices
    assert captured_state is not None
    email_indices = {rt.token_index for rt in captured_state.tokens.values() if rt.pii_type.name == "EMAIL"}
    assert email_indices == {1, 2}
