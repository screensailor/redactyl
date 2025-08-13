import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel


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


async def stream(
    input: Input,
) -> AsyncGenerator[StreamingResponse, Any]:
    await asyncio.sleep(0.1)
    yield StreamingResponse(part1=Part1(text="Part 1 of the response."))
    await asyncio.sleep(0.1)
    yield StreamingResponse(part2=Part2(text="Part 2 of the response."))
    await asyncio.sleep(0.1)
    yield StreamingResponse(
        done=True,
        complete=Complete(
            input=input,
            part1=Part1(text="Part 1 of the response."),
            part2=Part2(text="Part 2 of the response."),
        ),
    )
