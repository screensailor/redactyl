#!/usr/bin/env python
"""Test email redaction specifically."""

from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig
from pydantic import BaseModel


def test_email_direct():
    """Test email detection directly."""
    detector = PresidioDetector(
        use_gliner_for_names=False,  # Disable GLiNER to isolate email issue
        language="en",
    )
    
    loop = PIILoop(detector=detector)
    
    # Test simple email
    text = "Contact me at john.smith@example.com for more info."
    redacted, state = loop.redact(text)
    
    print("=" * 60)
    print("Direct Email Test")
    print("=" * 60)
    print(f"Original: {text}")
    print(f"Redacted: {redacted}")
    print(f"Tokens: {list(state.tokens.keys())}")
    
    # Check what entities were detected
    entities = detector.detect(text)
    print(f"\nDetected entities:")
    for entity in entities:
        print(f"  - {entity.type.name}: '{entity.value}' [{entity.start}:{entity.end}]")
    
    print("=" * 60)


def test_email_with_pii_config():
    """Test email with PIIConfig."""
    pii = PIIConfig()  # Use default config
    
    class SimpleModel(BaseModel):
        email: str
    
    captured = None
    
    @pii.protect
    def process(model: SimpleModel) -> SimpleModel:
        nonlocal captured
        captured = model
        return model
    
    model = SimpleModel(email="john.smith@example.com")
    result = process(model)
    
    print("\n" + "=" * 60)
    print("PIIConfig Email Test")
    print("=" * 60)
    print(f"Original: {model.email}")
    print(f"Redacted: {captured.email}")
    print(f"Restored: {result.email}")
    print("=" * 60)


if __name__ == "__main__":
    test_email_direct()
    test_email_with_pii_config()