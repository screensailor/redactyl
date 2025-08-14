"""Tests for streaming membrane and input-based state."""

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
    """Fake detector that finds specific names (inputs only)."""

    def detect(self, text: str) -> list[PIIEntity]:
        """Detect John Doe and John as person entities."""
        res: list[PIIEntity] = []
        for needle in ["John Doe", "John"]:
            start = text.find(needle)
            if start != -1:
                res.append(PIIEntity(PIIType.PERSON, needle, start, start + len(needle), 0.9))
        return res


@pytest.mark.asyncio
async def test_streaming_membrane_and_input_state_async():
    """Async generator yields unredacted values; on_stream_complete exposes input state."""
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
    async def gen(user: User):
        # Inside bubble: user is redacted; we simply echo it back
        yield user

    out = []
    async for item in gen(User(name="John Doe", email="a@b.com")):
        out.append(item)

    # Outside the bubble, values are unredacted
    assert out[0].name == "John Doe"
    # Accumulated state comes from inputs only
    assert captured_state is not None
    person_tokens = [t for t in captured_state.tokens if t.startswith("[PERSON_")]
    # Only the input name should produce a PERSON token
    assert set(person_tokens) == {"[PERSON_1]"}


def test_streaming_membrane_and_input_state_sync():
    """Sync generator yields unredacted values; on_stream_complete exposes input state."""
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
    def gen(user: User):
        # Inside bubble: user is redacted; we simply echo it back
        yield user

    out = list(gen(User(name="John Doe", email="a@b.com")))

    # Outside the bubble, values are unredacted
    assert out[0].name == "John Doe"
    # Accumulated state comes from inputs only
    assert captured_state is not None
    person_tokens = [t for t in captured_state.tokens if t.startswith("[PERSON_")]
    assert set(person_tokens) == {"[PERSON_1]"}
