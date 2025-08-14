"""Tests for container traversal in PII protection."""

from typing import Annotated
from pydantic import BaseModel

from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig, pii


class User(BaseModel):
    """Test model with PII fields."""
    name: str
    email: str
    internal_id: Annotated[str, pii(detect=False)]


def test_container_traversal_args_and_returns():
    """Test that container traversal works for args and returns."""
    config = PIIConfig(detector=PresidioDetector(), traverse_containers=True)
    captured = None

    @config.protect
    def proc(users: list[User]) -> list[User]:
        nonlocal captured
        captured = [u.model_copy() for u in users]
        return users

    users = [
        User(name="John Doe", email="john@example.com", internal_id="ID-123"),
        User(name="Jane Roe", email="jane@example.com", internal_id="ID-456"),
    ]

    result = proc(users)
    
    # Return should be unredacted
    assert result[0].name == "John Doe"
    assert result[1].email == "jane@example.com"
    
    # Inside the function, items were redacted
    assert captured is not None
    assert "[" in captured[0].name and "]" in captured[0].name
    assert "[EMAIL_" in captured[1].email
    
    # Non-detected field preserved
    assert captured[0].internal_id == "ID-123"
    assert captured[1].internal_id == "ID-456"


def test_nested_container_traversal():
    """Test nested container traversal."""
    config = PIIConfig(detector=PresidioDetector(), traverse_containers=True)

    @config.protect
    def proc(payload: dict[str, list[User]]) -> dict[str, list[User]]:
        return payload

    payload = {
        "users": [User(name="John Doe", email="john@example.com", internal_id="X")]
    }

    result = proc(payload)
    
    # Fully unredacted return
    assert result["users"][0].name == "John Doe"
    assert result["users"][0].email == "john@example.com"


def test_mixed_container_types():
    """Test various container types."""
    config = PIIConfig(detector=PresidioDetector(), traverse_containers=True)
    
    captured_tuple: tuple[User, str, User] | None = None
    captured_set: set[str] | None = None
    
    @config.protect
    def proc_tuple(data: tuple[User, str, User]) -> tuple[User, str, User]:
        nonlocal captured_tuple
        captured_tuple = data
        return data
    
    @config.protect 
    def proc_set(data: set[str]) -> set[str]:
        nonlocal captured_set
        captured_set = data.copy()
        return data
    
    # Test tuple with mixed types
    user1 = User(name="Alice", email="alice@test.com", internal_id="A1")
    user2 = User(name="Bob", email="bob@test.com", internal_id="B1")
    
    result_tuple = proc_tuple((user1, "separator", user2))
    
    assert result_tuple[0].name == "Alice"
    assert result_tuple[1] == "separator"  # Non-model unchanged
    assert result_tuple[2].name == "Bob"
    
    # Check captured values were redacted
    assert captured_tuple is not None
    assert "[" in captured_tuple[0].name
    assert captured_tuple[1] == "separator"  # String unchanged since not a model
    assert "[" in captured_tuple[2].name
    
    # Test set of strings with PII
    emails = {"john@example.com", "jane@example.com", "admin@example.com"}
    result_set = proc_set(emails)
    
    # Should be unredacted
    assert "john@example.com" in result_set
    assert "jane@example.com" in result_set
    
    # Captured should have been redacted
    assert captured_set is not None
    assert any("[EMAIL_" in s for s in captured_set)


def test_container_traversal_disabled():
    """Test that container traversal can be disabled."""
    config = PIIConfig(detector=PresidioDetector(), traverse_containers=False)
    
    @config.protect
    def proc(users: list[User]) -> list[User]:
        # With traverse_containers=False, list contents not processed
        return users
    
    users = [
        User(name="John Doe", email="john@example.com", internal_id="ID-123"),
    ]
    
    result = proc(users)
    
    # Should be unchanged since traverse_containers=False
    assert result[0].name == "John Doe"
    assert result[0].email == "john@example.com"


def test_raw_string_protection():
    """Test that raw strings get protected when traverse_containers=True."""
    config = PIIConfig(detector=PresidioDetector(), traverse_containers=True)
    
    captured = None
    
    @config.protect
    def proc(email: str) -> str:
        nonlocal captured
        captured = email
        return email
    
    result = proc("john.doe@example.com")
    
    # Result should be unredacted
    assert result == "john.doe@example.com"
    
    # But inside the function it was redacted
    assert captured is not None
    assert "[EMAIL_" in captured
    assert "john.doe@example.com" not in captured