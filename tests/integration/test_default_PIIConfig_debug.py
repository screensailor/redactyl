#!/usr/bin/env python
"""Debug default PIIConfig to see what's being detected."""

from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class UserProfile(BaseModel):
    """Test model with various PII fields."""
    name: str
    email: str
    bio: str
    phone: str


def test_debug_detection():
    """Debug what PII is actually being detected."""
    pii = PIIConfig()
    
    captured_redacted = None
    
    @pii.protect
    def process(user: UserProfile) -> UserProfile:
        nonlocal captured_redacted
        captured_redacted = user
        return user
    
    # Create test data with various PII
    user = UserProfile(
        name="John Smith",
        email="john.smith@example.com",
        bio="Contact me at 555-1234 or visit my office in New York.",
        phone="(555) 123-4567"
    )
    
    result = process(user)
    
    print("=" * 60)
    print("Debug: What was detected and redacted?")
    print("=" * 60)
    print(f"Original name:  '{user.name}'")
    print(f"Redacted name:  '{captured_redacted.name}'")
    print()
    print(f"Original email: '{user.email}'")
    print(f"Redacted email: '{captured_redacted.email}'")
    print()
    print(f"Original bio:   '{user.bio}'")
    print(f"Redacted bio:   '{captured_redacted.bio}'")
    print()
    print(f"Original phone: '{user.phone}'")
    print(f"Redacted phone: '{captured_redacted.phone}'")
    print("=" * 60)


if __name__ == "__main__":
    test_debug_detection()