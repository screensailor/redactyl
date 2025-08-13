"""Test the @pii.protect decorator with sync generator functions."""

from typing import Generator

from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class Message(BaseModel):
    text: str


class Response(BaseModel):
    message: Message
    step: int


# Create PII config
pii = PIIConfig()


@pii.protect
def process_messages(input: Message) -> Generator[Response, None, None]:
    """Sync generator that yields responses with PII."""
    yield Response(
        message=Message(text="User is Jane Doe from New York"),
        step=1
    )
    yield Response(
        message=Message(text="Email address is jane@example.com"),
        step=2
    )
    yield Response(
        message=Message(text=f"Original input: {input.text}"),
        step=3
    )


def test_sync_generator_decorator():
    """Test that the decorator handles sync generators correctly."""
    # Input with PII
    user_input = Message(text="Contact John Smith at john@example.com")
    
    # Collect all responses
    responses = list(process_messages(user_input))
    
    # Verify we got 3 responses
    assert len(responses) == 3
    
    # Check first response
    assert responses[0].step == 1
    assert "Jane Doe" not in responses[0].message.text
    assert ("[NAME_" in responses[0].message.text or "[PERSON_" in responses[0].message.text)
    assert "New York" not in responses[0].message.text
    assert "[LOCATION_" in responses[0].message.text
    
    # Check second response
    assert responses[1].step == 2
    assert "jane@example.com" not in responses[1].message.text
    assert "[EMAIL_" in responses[1].message.text
    
    # Check third response (echoes protected input)
    assert responses[2].step == 3
    assert "John Smith" not in responses[2].message.text
    assert "john@example.com" not in responses[2].message.text
    assert "[NAME_" in responses[2].message.text
    assert "[EMAIL_" in responses[2].message.text


def test_sync_generator_with_non_model_yields():
    """Test sync generator that yields mixed types."""
    
    @pii.protect
    def mixed_generator(msg: Message) -> Generator[Response | str, None, None]:
        yield "Starting processing..."
        yield Response(message=Message(text="Found: Alice Brown"), step=1)
        yield "Finishing up..."
    
    results = list(mixed_generator(Message(text="Test")))
    
    assert len(results) == 3
    assert results[0] == "Starting processing..."
    assert isinstance(results[1], Response)
    assert "Alice Brown" not in results[1].message.text
    assert results[2] == "Finishing up..."