#!/usr/bin/env python
"""Debug email detection in batch mode."""

from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig
from redactyl.detectors.presidio import PresidioDetector


class UserProfile(BaseModel):
    """Test model with various PII fields."""
    name: str
    email: str


def test_batch_email():
    """Test email detection in batch mode."""
    # Create detector without GLiNER first
    detector = PresidioDetector(
        use_gliner_for_names=False,
        language="en",
    )
    
    pii = PIIConfig(
        detector=detector,
        batch_detection=True,
        use_name_parsing=False,
    )
    
    captured = None
    
    @pii.protect
    def process(user: UserProfile) -> UserProfile:
        nonlocal captured
        captured = user
        return user
    
    user = UserProfile(
        name="John Smith",
        email="john.smith@example.com"
    )
    
    result = process(user)
    
    print("=" * 60)
    print("Batch Email Test (No GLiNER)")
    print("=" * 60)
    print(f"Original email: '{user.email}'")
    print(f"Redacted email: '{captured.email}'")
    print(f"Restored email: '{result.email}'")
    
    # Now test with GLiNER
    detector2 = PresidioDetector(
        use_gliner_for_names=True,
        language="en",
    )
    
    pii2 = PIIConfig(
        detector=detector2,
        batch_detection=True,
        use_name_parsing=True,
    )
    
    captured2 = None
    
    @pii2.protect
    def process2(user: UserProfile) -> UserProfile:
        nonlocal captured2
        captured2 = user
        return user
    
    result2 = process2(user)
    
    print("\n" + "=" * 60)
    print("Batch Email Test (With GLiNER)")
    print("=" * 60)
    print(f"Original email: '{user.email}'")
    print(f"Redacted email: '{captured2.email}'")
    print(f"Restored email: '{result2.email}'")
    
    # Test direct detection
    entities = detector2.detect(user.email)
    print(f"\nDirect detection of email:")
    for entity in entities:
        print(f"  - {entity.type.name}: '{entity.value}' [{entity.start}:{entity.end}]")
    
    print("=" * 60)


if __name__ == "__main__":
    test_batch_email()