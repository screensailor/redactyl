"""
Proof of concept for dynamic PII detection in redactyl.

This example demonstrates how to handle fields where we don't know
ahead of time if they contain PII.
"""

from typing import Annotated, Any, Literal, TypeAlias
from pydantic import BaseModel, Field
from enum import Enum, auto
from dataclasses import dataclass
import re

# Import from existing redactyl
from redactyl.types import PIIType, PIIEntity
from redactyl.detectors import BaseDetector
from redactyl.core import PIILoop


class DetectionStrategy(Enum):
    """How to detect PII in a field."""
    STATIC = auto()      # Field is always PII of known type
    DYNAMIC = auto()     # Field might contain PII, needs scanning
    HYBRID = auto()      # Field has known type but might contain others


@dataclass
class PIIFieldMetadata:
    """Metadata for PII field configuration."""
    strategy: DetectionStrategy = DetectionStrategy.STATIC
    types: list[PIIType] | None = None
    confidence_threshold: float = 0.7
    scan_depth: Literal["shallow", "deep"] = "shallow"


# Type aliases for ergonomic API
StaticPII: TypeAlias = Annotated[str, PIIFieldMetadata(strategy=DetectionStrategy.STATIC)]
DynamicPII: TypeAlias = Annotated[str, PIIFieldMetadata(strategy=DetectionStrategy.DYNAMIC)]
HybridPII: TypeAlias = Annotated[str, PIIFieldMetadata(strategy=DetectionStrategy.HYBRID)]


def pii_field(
    *types: PIIType,
    strategy: DetectionStrategy = DetectionStrategy.STATIC,
    confidence_threshold: float = 0.7,
    scan_depth: Literal["shallow", "deep"] = "shallow"
) -> PIIFieldMetadata:
    """Create PII field metadata with specified configuration."""
    return PIIFieldMetadata(
        strategy=strategy,
        types=list(types) if types else None,
        confidence_threshold=confidence_threshold,
        scan_depth=scan_depth
    )


# Example models demonstrating the API
class SupportTicket(BaseModel):
    """Example model with mixed PII detection strategies."""
    
    # Static fields - we know what they are
    id: str
    user_email: Annotated[str, pii_field(PIIType.EMAIL)]
    
    # Dynamic fields - might contain PII
    subject: Annotated[str, pii_field(strategy=DetectionStrategy.DYNAMIC)]
    description: Annotated[str, pii_field(
        strategy=DetectionStrategy.DYNAMIC,
        scan_depth="deep"
    )]
    
    # Hybrid field - primarily one type but might have others
    internal_notes: Annotated[str, pii_field(
        PIIType.PERSON,  # Usually contains customer names
        strategy=DetectionStrategy.HYBRID,
        confidence_threshold=0.8
    )]


class UserProfile(BaseModel):
    """Example with simple static fields and complex dynamic field."""
    
    # Clean ergonomic API for simple cases
    email: Annotated[str, pii_field(PIIType.EMAIL)]
    phone: Annotated[str, pii_field(PIIType.PHONE)]
    
    # Complex field with multiple possible PII types
    bio: Annotated[str, pii_field(
        PIIType.EMAIL, PIIType.PHONE, PIIType.ADDRESS,
        strategy=DetectionStrategy.DYNAMIC
    )]


# Simple detector implementation for demo
class SimpleDynamicDetector(BaseDetector):
    """Basic detector supporting both static and dynamic detection."""
    
    # Simple regex patterns for demo
    patterns = {
        PIIType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        PIIType.PHONE: r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        PIIType.PERSON: r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',  # Simple name pattern
        PIIType.SSN: r'\b\d{3}-\d{2}-\d{4}\b',
        PIIType.CREDIT_CARD: r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
    }
    
    def detect(self, text: str) -> list[PIIEntity]:
        """Detect all PII in text (used by base PIILoop)."""
        entities = []
        
        for pii_type, pattern in self.patterns.items():
            for match in re.finditer(pattern, text):
                entities.append(PIIEntity(
                    type=pii_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9  # Simple detector, high confidence
                ))
        
        return entities
    
    def detect_static(self, text: str, pii_type: PIIType) -> list[PIIEntity]:
        """Optimized detection for known type."""
        entities = []
        pattern = self.patterns.get(pii_type)
        
        if pattern:
            for match in re.finditer(pattern, text):
                entities.append(PIIEntity(
                    type=pii_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95  # Higher confidence for targeted search
                ))
        
        return entities
    
    def detect_dynamic(self, text: str, scan_depth: str = "shallow") -> list[PIIEntity]:
        """Comprehensive scan for any PII."""
        # In real implementation, this would use NLP, context analysis, etc.
        # For demo, we just use all patterns
        return self.detect(text)


def demonstrate_dynamic_detection():
    """Show how dynamic detection works in practice."""
    
    # Create a support ticket with mixed content
    ticket = SupportTicket(
        id="TICKET-12345",
        user_email="john.doe@example.com",
        subject="Account access issue",
        description="I can't log in with john.doe@example.com. My phone 415-555-0123 isn't receiving codes.",
        internal_notes="Customer John Smith called from 415-555-0123 about email john.doe@example.com"
    )
    
    print("Original ticket:")
    print(f"  Email: {ticket.user_email}")
    print(f"  Subject: {ticket.subject}")
    print(f"  Description: {ticket.description}")
    print(f"  Notes: {ticket.internal_notes}")
    print()
    
    # Create detector and PIILoop
    detector = SimpleDynamicDetector()
    redactyl = PIILoop(detector)
    
    # Process each field based on its metadata
    print("Processing with field metadata:")
    
    # Static field - we know it's an email
    email_text, email_state = redactyl.redact(ticket.user_email)
    print(f"  Email (static): {email_text}")
    
    # Dynamic field - scan for any PII
    desc_text, desc_state = redactyl.redact(ticket.description)
    print(f"  Description (dynamic): {desc_text}")
    
    # Hybrid field - expect names but might have more
    notes_text, notes_state = redactyl.redact(ticket.internal_notes)
    print(f"  Notes (hybrid): {notes_text}")
    print()
    
    # Show detected PII types
    print("Detected PII:")
    all_tokens = {**email_state.tokens, **desc_state.tokens, **notes_state.tokens}
    for token, redaction in all_tokens.items():
        print(f"  {token}: '{redaction.original}' (type: {redaction.pii_type.name})")


if __name__ == "__main__":
    demonstrate_dynamic_detection()