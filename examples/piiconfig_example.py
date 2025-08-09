#!/usr/bin/env python3
"""Example demonstrating PIIConfig for improved decorator API."""

from pydantic import BaseModel

from redactyl.detectors.smart_mock import SmartMockDetector
from redactyl.pydantic_integration import (
    HallucinationResponse,
    PIIConfig,
)
from redactyl.types import PIIType


class User(BaseModel):
    """User model with PII fields."""

    name: str
    email: str
    phone: str | None = None
    notes: str = ""


def main():
    """Demonstrate PIIConfig usage."""
    # Setup detector
    detector = SmartMockDetector([
        ("John Doe", PIIType.PERSON),
        ("john@example.com", PIIType.EMAIL),
        ("555-0123", PIIType.PHONE),
    ])

    # Example 1: Basic PIIConfig usage
    print("Example 1: Basic PIIConfig")
    print("-" * 40)

    config = PIIConfig(detector=detector)

    @config.protect
    def process_user_basic(user: User) -> User:
        """Process user with automatic PII protection."""
        print(f"Inside function - Protected name: {user.name}")
        print(f"Inside function - Protected email: {user.email}")
        
        # Modify the user
        result = user.model_copy()
        result.notes = f"Processed user {user.name} with email {user.email}"
        return result

    user = User(
        name="John Doe",
        email="john@example.com",
        phone="555-0123",
        notes="Important customer"
    )

    print(f"Original user: {user}")
    result = process_user_basic(user)
    print(f"Result user: {result}")
    print()

    # Example 2: PIIConfig with hallucination handling
    print("Example 2: Hallucination Handling")
    print("-" * 40)

    def handle_hallucinations(issues):
        """Custom hallucination handler."""
        print(f"Detected {len(issues)} hallucinated tokens:")
        responses = []
        for issue in issues:
            print(f"  - {issue.token}: {issue.issue_type}")
            
            if "EMAIL" in issue.token:
                # Replace unknown emails with placeholder
                responses.append(HallucinationResponse.replace("[REDACTED_EMAIL]"))
            elif "PHONE" in issue.token:
                # Remove phone tokens entirely
                responses.append(HallucinationResponse.ignore())
            elif "SSN" in issue.token:
                # Throw on SSN for security
                responses.append(HallucinationResponse.throw())
            else:
                # Preserve other tokens
                responses.append(HallucinationResponse.preserve())
        
        return responses

    config_with_handler = PIIConfig(
        detector=detector,
        on_hallucination=handle_hallucinations
    )

    @config_with_handler.protect
    def process_with_hallucinations(user: User) -> User:
        """Simulate LLM hallucinating new PII tokens."""
        result = user.model_copy()
        # Simulate LLM adding new tokens
        result.notes = (
            f"Contact {user.name} at {user.email} or [EMAIL_99] "
            f"or call [PHONE_99]. Reference: [REF_123]"
        )
        return result

    user2 = User(
        name="John Doe",
        email="john@example.com"
    )

    print(f"Original user: {user2}")
    result2 = process_with_hallucinations(user2)
    print(f"Result after handling hallucinations: {result2}")
    print()

    # Example 3: Strict mode - throw on any hallucination
    print("Example 3: Strict Mode")
    print("-" * 40)

    strict_config = PIIConfig(
        detector=detector,
        on_hallucination=lambda issues: [
            HallucinationResponse.throw() for _ in issues
        ]
    )

    @strict_config.protect
    def strict_process(user: User) -> User:
        """Process with strict hallucination checking."""
        result = user.model_copy()
        # This would throw an exception if there were hallucinated tokens
        result.notes = f"Processed {user.name}"
        return result

    user3 = User(name="John Doe", email="john@example.com")
    
    try:
        print(f"Original user: {user3}")
        result3 = strict_process(user3)
        print(f"Strict mode result: {result3}")
        print("No hallucinations detected!")
    except Exception as e:
        print(f"Strict mode threw exception: {e}")

    print()

    # Example 4: Different configurations for different use cases
    print("Example 4: Multiple Configurations")
    print("-" * 40)

    # Lenient config for development
    dev_config = PIIConfig(
        detector=detector,
        on_hallucination=lambda issues: [
            HallucinationResponse.preserve() for _ in issues
        ]
    )

    # Production config with custom handling
    prod_config = PIIConfig(
        detector=detector,
        batch_detection=True,  # Optimize for production
        on_hallucination=lambda issues: [
            HallucinationResponse.replace("[MASKED]") 
            if "EMAIL" in issue.token or "PHONE" in issue.token
            else HallucinationResponse.preserve()
            for issue in issues
        ]
    )

    @dev_config.protect
    def dev_process(user: User) -> User:
        """Development processing - lenient."""
        result = user.model_copy()
        result.notes = "Dev: [UNKNOWN_TOKEN_1]"
        return result

    @prod_config.protect
    def prod_process(user: User) -> User:
        """Production processing - strict."""
        result = user.model_copy()
        result.notes = "Prod: [EMAIL_99]"
        return result

    user4 = User(name="John Doe", email="john@example.com")
    
    print("Development mode:")
    dev_result = dev_process(user4)
    print(f"  Result: {dev_result.notes}")
    
    print("Production mode:")
    prod_result = prod_process(user4)
    print(f"  Result: {prod_result.notes}")


if __name__ == "__main__":
    main()