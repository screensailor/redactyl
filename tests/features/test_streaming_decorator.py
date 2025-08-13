"""Test the @pii.protect decorator with streaming generator functions."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class Input(BaseModel):
    text: str


class Part1(BaseModel):
    text: str


class Part2(BaseModel):
    text: str


class Complete(BaseModel):
    input: Input
    part1: Part1
    part2: Part2


class StreamingResponse(BaseModel):
    done: bool = False
    part1: Part1 | None = None
    part2: Part2 | None = None
    complete: Complete | None = None


# Create PII config
pii = PIIConfig()


@pii.protect
async def stream(
    input: Input,
) -> AsyncGenerator[StreamingResponse, Any]:
    """Streaming function that yields responses with PII."""
    # Inside the function, input.text contains tokens like [NAME_FIRST_1] [EMAIL_1]
    # We can:
    # 1. Reference these tokens in our yields (they'll be unredacted)
    # 2. Introduce new hardcoded values
    await asyncio.sleep(0.01)
    
    # Yield response that references input tokens
    yield StreamingResponse(
        part1=Part1(text=f"Processing request from [NAME_FIRST_1] [NAME_LAST_1]")
    )
    await asyncio.sleep(0.01)
    
    # Yield response with mixed content
    yield StreamingResponse(
        part2=Part2(text=f"Will respond to [EMAIL_1] (via our Jane Doe handler)")
    )
    
    await asyncio.sleep(0.01)
    # Echo the input back
    yield StreamingResponse(
        done=True,
        complete=Complete(
            input=input,  # This will be unredacted when yielded
            part1=Part1(text=f"Processing request from [NAME_FIRST_1] [NAME_LAST_1]"),
            part2=Part2(text=f"Will respond to [EMAIL_1]"),
        ),
    )


@pytest.mark.asyncio
async def test_streaming_decorator():
    """Streaming yields are unredacted to the caller while internal state is maintained."""
    # Input with PII
    user_input = Input(text="My name is John Smith and my email is john@example.com")

    # Collect all responses
    responses = []
    async for response in stream(user_input):
        responses.append(response)

    # Verify we got 3 responses
    assert len(responses) == 3

    # Check first response (part1) - tokens are unredacted to input values
    assert responses[0].part1 is not None
    assert "John Smith" in responses[0].part1.text  # [NAME_FIRST_1] [NAME_LAST_1] → John Smith

    # Check second response (part2) - mixed content
    assert responses[1].part2 is not None
    assert "john@example.com" in responses[1].part2.text  # [EMAIL_1] → john@example.com
    assert "Jane Doe" in responses[1].part2.text  # Hardcoded value passes through

    # Check final response with complete data
    assert responses[2].done is True
    assert responses[2].complete is not None

    # The input should be unredacted back to original values
    assert responses[2].complete.input.text == user_input.text
    # And other parts show tokens are properly unredacted
    assert "John Smith" in responses[2].complete.part1.text
    assert "john@example.com" in responses[2].complete.part2.text


@pytest.mark.asyncio
async def test_streaming_consistent_tokens():
    """Sanity check that streaming still works and yields unredacted values."""
    user_input = Input(text="Contact Alice Brown at alice@example.com")

    responses = []
    async for response in stream(user_input):
        responses.append(response)

    # Verify unredacted values are visible outside the bubble
    # The generator yields text with tokens that get unredacted to the original input values
    assert any("Alice Brown" in r.part1.text for r in responses if r.part1)
    assert any("alice@example.com" in r.part2.text for r in responses if r.part2)
    assert any("Jane Doe" in r.part2.text for r in responses if r.part2)  # Hardcoded value
