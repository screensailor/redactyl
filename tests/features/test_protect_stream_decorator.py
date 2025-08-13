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


pii = PIIConfig()


@pii.protect
async def stream(
    input: Input,
) -> AsyncGenerator[StreamingResponse, Any]:
    # input is redacted here!
    await asyncio.sleep(0.1)
    part_1 = Part1(text="Part 1 about [NAME_FIRST_1].")
    yield StreamingResponse(part1=part_1)
    await asyncio.sleep(0.1)
    part_2 = Part2(text="Part 2 about [NAME_FIRST_1] [NAME_LAST_1].")
    yield StreamingResponse(part2=part_2)
    await asyncio.sleep(0.1)
    yield StreamingResponse(
        done=True,
        complete=Complete(
            input=input,
            part1=part_1,
            part2=part_2,
        ),
    )


@pytest.mark.asyncio
async def test_streaming_decorator():
    input = Input(text="Hi, I'm John. Kind regards, John Doe")

    responses = []
    async for response in stream(input):
        responses.append(response)

    # all responses should be unredacted!
    # from outside `stream` it is as if we never redacted anything
