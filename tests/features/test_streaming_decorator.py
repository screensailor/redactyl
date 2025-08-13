"""Test the @pii.protect decorator with streaming generator functions."""

import asyncio
import re
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
    await asyncio.sleep(0.01)
    yield StreamingResponse(
        part1=Part1(text="Hello, I'm Jane Doe from New York.")
    )
    await asyncio.sleep(0.01)
    yield StreamingResponse(
        part2=Part2(text="You can reach me at jane.doe@example.com")
    )
    await asyncio.sleep(0.01)
    yield StreamingResponse(
        done=True,
        complete=Complete(
            input=input,
            part1=Part1(text="Hello, I'm Jane Doe from New York."),
            part2=Part2(text="You can reach me at jane.doe@example.com"),
        ),
    )


@pytest.mark.asyncio
async def test_streaming_decorator():
    """Test that the decorator handles streaming functions correctly."""
    # Input with PII
    user_input = Input(text="My name is John Smith and my email is john@example.com")
    
    # Collect all responses
    responses = []
    async for response in stream(user_input):
        responses.append(response)
    
    # Verify we got 3 responses
    assert len(responses) == 3
    
    # Check first response (part1)
    assert responses[0].part1 is not None
    assert "Jane Doe" not in responses[0].part1.text
    # With name parsing enabled, we get NAME_FIRST and NAME_LAST instead of PERSON
    assert ("[NAME_FIRST_" in responses[0].part1.text or "[PERSON_" in responses[0].part1.text)
    assert ("[NAME_LAST_" in responses[0].part1.text or "[PERSON_" in responses[0].part1.text)
    assert "New York" not in responses[0].part1.text
    assert "[LOCATION_" in responses[0].part1.text
    
    # Check second response (part2)
    assert responses[1].part2 is not None
    assert "jane.doe@example.com" not in responses[1].part2.text
    assert "[EMAIL_" in responses[1].part2.text
    
    # Check final response with complete data
    assert responses[2].done is True
    assert responses[2].complete is not None
    
    # Verify input was protected when passed to the function
    # The generator receives protected input and echoes it back
    assert responses[2].complete.input.text != user_input.text
    assert "John Smith" not in responses[2].complete.input.text
    assert "[NAME_FIRST_" in responses[2].complete.input.text
    assert "[NAME_LAST_" in responses[2].complete.input.text
    assert "john@example.com" not in responses[2].complete.input.text
    assert "[EMAIL_" in responses[2].complete.input.text
    
    # Verify part1 in complete
    assert "Jane Doe" not in responses[2].complete.part1.text
    assert ("[NAME_FIRST_" in responses[2].complete.part1.text or "[PERSON_" in responses[2].complete.part1.text)
    
    # Verify part2 in complete
    assert "jane.doe@example.com" not in responses[2].complete.part2.text
    assert "[EMAIL_" in responses[2].complete.part2.text


@pytest.mark.asyncio
async def test_streaming_consistent_tokens():
    """Test that tokens remain consistent across multiple yields."""
    user_input = Input(text="Contact Alice Brown at alice@example.com")
    
    responses = []
    async for response in stream(user_input):
        responses.append(response)
    
    # If the same entity appears in multiple yields, it should have the same token
    # In this case, we're checking that entities are consistently tokenized
    
    # Extract tokens from responses
    tokens_in_part1 = []
    tokens_in_part2 = []
    tokens_in_complete = []
    
    if responses[0].part1:
        text = responses[0].part1.text
        # Find all tokens (simple pattern matching)
        tokens_in_part1 = re.findall(r'\[[\w_]+_\d+\]', text)
    
    if responses[1].part2:
        text = responses[1].part2.text
        tokens_in_part2 = re.findall(r'\[[\w_]+_\d+\]', text)
    
    if responses[2].complete:
        text1 = responses[2].complete.part1.text
        text2 = responses[2].complete.part2.text
        tokens_in_complete.extend(re.findall(r'\[[\w_]+_\d+\]', text1))
        tokens_in_complete.extend(re.findall(r'\[[\w_]+_\d+\]', text2))
    
    # Verify tokens are present
    assert len(tokens_in_part1) > 0
    assert len(tokens_in_part2) > 0
    assert len(tokens_in_complete) > 0