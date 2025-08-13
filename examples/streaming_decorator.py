"""
Example of using @pii.protect decorator with streaming generator functions.

The decorator supports both async and sync generators that yield Pydantic models.
It automatically protects PII in:
1. Input arguments passed to the generator
2. Each yielded model

This is useful for streaming APIs (like LLM responses) where you want to
protect PII in real-time as data streams through your application.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


# Define your models
class UserInput(BaseModel):
    query: str
    user_email: str


class StreamingChunk(BaseModel):
    content: str
    chunk_index: int
    done: bool = False


# Create PII configuration
pii = PIIConfig()


# Example 1: Async streaming generator
@pii.protect
async def stream_response(
    user_input: UserInput,
) -> AsyncGenerator[StreamingChunk, Any]:
    """
    Async generator that streams responses with PII protection.
    
    The decorator will:
    1. Protect the user_input before passing it to the function
    2. Protect each yielded StreamingChunk before returning it
    """
    # The user_input here already has PII redacted
    print(f"Processing query: {user_input.query}")
    print(f"User email (protected): {user_input.user_email}")
    
    # Simulate streaming response
    await asyncio.sleep(0.1)
    yield StreamingChunk(
        content="Hello John Doe, I found your account.",
        chunk_index=0
    )
    
    await asyncio.sleep(0.1)
    yield StreamingChunk(
        content="Your address is 123 Main St, New York.",
        chunk_index=1
    )
    
    await asyncio.sleep(0.1)
    yield StreamingChunk(
        content="Contact email: john.doe@example.com",
        chunk_index=2,
        done=True
    )


# Example 2: Sync streaming generator
@pii.protect
def process_batch(
    user_input: UserInput,
) -> Generator[StreamingChunk, None, None]:
    """
    Sync generator with PII protection.
    
    Works the same as async but for synchronous code.
    """
    # Process in batches
    yield StreamingChunk(
        content=f"Processing request from {user_input.user_email}",
        chunk_index=0
    )
    
    yield StreamingChunk(
        content="Found user: Alice Brown, SSN: 123-45-6789",
        chunk_index=1
    )
    
    yield StreamingChunk(
        content="Phone: 555-1234, Email: alice@example.com",
        chunk_index=2,
        done=True
    )


async def main():
    """Demonstrate streaming with PII protection."""
    
    # Create input with PII
    user_input = UserInput(
        query="Find my account information",
        user_email="real.user@company.com"
    )
    
    print("=" * 50)
    print("ASYNC STREAMING EXAMPLE")
    print("=" * 50)
    
    # The decorator protects PII in the input and all yielded chunks
    async for chunk in stream_response(user_input):
        print(f"Chunk {chunk.chunk_index}: {chunk.content}")
        if chunk.done:
            print("Stream complete!")
    
    print("\n" + "=" * 50)
    print("SYNC STREAMING EXAMPLE")
    print("=" * 50)
    
    # Sync generator works the same way
    for chunk in process_batch(user_input):
        print(f"Chunk {chunk.chunk_index}: {chunk.content}")
        if chunk.done:
            print("Stream complete!")


if __name__ == "__main__":
    asyncio.run(main())
    
    print("\n" + "=" * 50)
    print("KEY POINTS:")
    print("=" * 50)
    print("1. PII in input arguments is automatically protected")
    print("2. Each yielded model has its PII protected")
    print("3. Protection state is maintained across all yields")
    print("4. Works with both async and sync generators")
    print("5. Non-model yields pass through unchanged")