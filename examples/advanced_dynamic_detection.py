"""
Advanced dynamic PII detection with model-aware processing.

This example shows how to integrate dynamic detection with Pydantic models
and handle complex real-world scenarios.
"""

from typing import Annotated, Any, get_args, get_origin
from pydantic import BaseModel
from dataclasses import dataclass
import re

from redactyl.types import PIIType, PIIEntity, RedactionState
from redactyl.core import PIILoop
from redactyl.detectors import BaseDetector

# Import from our POC
from dynamic_detection_poc import (
    DetectionStrategy, PIIFieldMetadata, pii_field,
    SimpleDynamicDetector
)


@dataclass
class DetectionContext:
    """Context for PII detection including field metadata."""
    field_name: str
    field_metadata: PIIFieldMetadata
    parent_model: type[BaseModel] | None = None


class EnhancedPIIDetector(BaseDetector):
    """Detector that understands field context and strategies."""
    
    def __init__(self, base_detector: BaseDetector):
        self.base_detector = base_detector
    
    def detect(self, text: str) -> list[PIIEntity]:
        """Default detection (fallback to base)."""
        return self.base_detector.detect(text)
    
    def detect_with_context(self, text: str, context: DetectionContext) -> list[PIIEntity]:
        """Context-aware detection using field metadata."""
        metadata = context.field_metadata
        
        if metadata.strategy == DetectionStrategy.STATIC:
            # Fast path - only look for specified types
            if hasattr(self.base_detector, 'detect_static'):
                entities = []
                for pii_type in metadata.types or []:
                    entities.extend(
                        self.base_detector.detect_static(text, pii_type)
                    )
                return entities
            else:
                # Fallback to general detection and filter
                all_entities = self.detect(text)
                return [e for e in all_entities if e.type in (metadata.types or [])]
        
        elif metadata.strategy == DetectionStrategy.DYNAMIC:
            # Full scan with confidence filtering
            entities = self.detect(text)
            return [e for e in entities if e.confidence >= metadata.confidence_threshold]
        
        else:  # HYBRID
            # Start with known types at higher confidence
            static_entities = []
            if hasattr(self.base_detector, 'detect_static'):
                for pii_type in metadata.types or []:
                    static_entities.extend(
                        self.base_detector.detect_static(text, pii_type)
                    )
            
            # Also do full scan
            dynamic_entities = self.detect(text)
            
            # Merge, preferring static detections
            return self._merge_entities(static_entities, dynamic_entities, metadata)
    
    def _merge_entities(
        self, 
        static: list[PIIEntity], 
        dynamic: list[PIIEntity],
        metadata: PIIFieldMetadata
    ) -> list[PIIEntity]:
        """Merge static and dynamic detections, avoiding duplicates."""
        # Simple merge - in production, handle overlaps better
        seen_positions = {(e.start, e.end) for e in static}
        
        merged = list(static)
        for entity in dynamic:
            if (entity.start, entity.end) not in seen_positions:
                if entity.confidence >= metadata.confidence_threshold:
                    merged.append(entity)
        
        return sorted(merged, key=lambda e: e.start)


class ModelAwarePIILoop(PIILoop):
    """PIILoop that understands Pydantic model annotations."""
    
    def __init__(self, detector: EnhancedPIIDetector):
        super().__init__(detector)
        self.enhanced_detector = detector
    
    def redact_model(self, instance: BaseModel) -> tuple[dict[str, Any], RedactionState]:
        """Redact PII from a Pydantic model instance."""
        redacted_data = {}
        combined_state = RedactionState()
        
        for field_name, field_info in instance.model_fields.items():
            value = getattr(instance, field_name)
            
            # Only process string fields
            if not isinstance(value, str):
                redacted_data[field_name] = value
                continue
            
            # Extract PII metadata from annotations
            metadata = self._extract_pii_metadata(field_info)
            if metadata is None:
                # No PII annotation, keep as-is
                redacted_data[field_name] = value
                continue
            
            # Create detection context
            context = DetectionContext(
                field_name=field_name,
                field_metadata=metadata,
                parent_model=type(instance)
            )
            
            # Detect with context
            entities = self.enhanced_detector.detect_with_context(value, context)
            
            # Use parent's redaction logic
            redacted_text, state = self._redact_with_entities(value, entities)
            
            redacted_data[field_name] = redacted_text
            combined_state = combined_state.merge(state)
        
        return redacted_data, combined_state
    
    def _extract_pii_metadata(self, field_info) -> PIIFieldMetadata | None:
        """Extract PII metadata from field annotations."""
        # Handle Annotated types
        if hasattr(field_info, 'annotation'):
            origin = get_origin(field_info.annotation)
            if origin is Annotated:
                args = get_args(field_info.annotation)
                for arg in args[1:]:  # Skip the base type
                    if isinstance(arg, PIIFieldMetadata):
                        return arg
        return None
    
    def _redact_with_entities(
        self, 
        text: str, 
        entities: list[PIIEntity]
    ) -> tuple[str, RedactionState]:
        """Reuse parent's redaction logic with detected entities."""
        # Filter and sort entities
        entities = self._filter_overlapping_entities(entities)
        
        # Build redaction state
        state = RedactionState()
        redacted_text = text
        
        # Process in reverse order
        token_counters: dict[str, int] = {}
        for entity in reversed(entities):
            # Get token index
            type_name = entity.type.name
            if type_name not in token_counters:
                token_counters[type_name] = 0
            token_counters[type_name] += 1
            
            # Create token
            from redactyl.types import RedactionToken
            token = RedactionToken(
                original=entity.value,
                pii_type=entity.type,
                token_index=token_counters[type_name],
                entity=entity
            )
            
            # Update state and text
            state = state.with_token(token.token, token)
            redacted_text = (
                redacted_text[:entity.start] + 
                token.token + 
                redacted_text[entity.end:]
            )
        
        return redacted_text, state


# Real-world example models
class CustomerInteraction(BaseModel):
    """Model representing a customer service interaction."""
    
    interaction_id: str
    timestamp: str
    
    # Known PII fields
    customer_email: Annotated[str, pii_field(PIIType.EMAIL)]
    agent_id: str  # Not PII
    
    # Dynamic content fields
    chat_transcript: Annotated[str, pii_field(
        strategy=DetectionStrategy.DYNAMIC,
        scan_depth="deep",
        confidence_threshold=0.6
    )]
    
    resolution_notes: Annotated[str, pii_field(
        PIIType.PERSON,  # Expect names
        strategy=DetectionStrategy.HYBRID,
        confidence_threshold=0.7
    )]


def demonstrate_model_aware_redaction():
    """Show model-aware redaction in action."""
    
    # Create a complex interaction
    interaction = CustomerInteraction(
        interaction_id="INT-2024-001",
        timestamp="2024-01-15T10:30:00Z",
        customer_email="jane.smith@example.com",
        agent_id="AGENT-42",
        chat_transcript="""
Customer: Hi, I need help with my account
Agent: Hello! I can help you with that. Can you provide your email?
Customer: Sure, it's jane.smith@example.com
Agent: Thank you. For security, can you verify the phone number on file?
Customer: Yes, it's 555-0123. Also, my billing address is 123 Main St, Anytown, CA 94105
Agent: Perfect, I've verified your account. How can I help today?
        """,
        resolution_notes="Helped Jane Smith update billing address and phone number 555-0123"
    )
    
    print("Original interaction:")
    print(f"  Customer email: {interaction.customer_email}")
    print(f"  Chat transcript preview: {interaction.chat_transcript[:100]}...")
    print(f"  Resolution notes: {interaction.resolution_notes}")
    print()
    
    # Create enhanced detector and model-aware loop
    base_detector = SimpleDynamicDetector()
    enhanced_detector = EnhancedPIIDetector(base_detector)
    redactyl = ModelAwarePIILoop(enhanced_detector)
    
    # Redact the entire model
    redacted_data, redaction_state = redactyl.redact_model(interaction)
    
    print("Redacted interaction:")
    print(f"  Customer email: {redacted_data['customer_email']}")
    print(f"  Agent ID: {redacted_data['agent_id']}")  # Not redacted
    print(f"  Chat transcript: {redacted_data['chat_transcript']}")
    print(f"  Resolution notes: {redacted_data['resolution_notes']}")
    print()
    
    print("Detected PII summary:")
    pii_counts = {}
    for token, redaction in redaction_state.tokens.items():
        pii_type = redaction.pii_type.name
        pii_counts[pii_type] = pii_counts.get(pii_type, 0) + 1
    
    for pii_type, count in pii_counts.items():
        print(f"  {pii_type}: {count} instance(s)")
    
    # Demonstrate unredaction
    print("\nUnredacting resolution notes:")
    unredacted_notes, issues = redactyl.unredact(
        redacted_data['resolution_notes'], 
        redaction_state
    )
    print(f"  Result: {unredacted_notes}")
    if issues:
        print(f"  Issues: {issues}")


if __name__ == "__main__":
    demonstrate_model_aware_redaction()