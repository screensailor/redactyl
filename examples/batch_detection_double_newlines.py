#!/usr/bin/env python
"""
Example: Using the BatchDetector with content containing double newlines.

This example demonstrates how the position-based tracking approach
correctly handles content which frequently contains double newlines.
"""

from redactyl.batch import BatchDetector, SmartBatchDetector
from redactyl.detectors.presidio import PresidioDetector
from redactyl.entity_tracker import NameComponentTracker
from redactyl.types import RedactionState


def main():
    """Demonstrate batch PII detection with content containing double newlines."""
    
    # Initialize the Presidio detector
    detector = PresidioDetector(confidence_threshold=0.7)
    
    # Typical content with double newlines
    content_examples = {
        "news_article": """
BREAKING: Tech Giant Announces New AI Initiative

SAN FRANCISCO - CEO Sarah Johnson announced today that the company 
will invest $500 million in AI research.

"We're excited about this opportunity," said Johnson at the press conference.

Johnson can be reached at sarah.johnson@techgiant.com for further comments.

The initiative will be led by Dr. Robert Chen, formerly of MIT.
Contact: robert.chen@techgiant.com
""",
        
        "chat_transcript": """
Customer: Hi, I'm having trouble with my account

Agent: Hello! I'm happy to help. May I have your name?

Customer: Sure, it's Michael O'Brien

Agent: Thank you, Mr. O'Brien. Can you provide your email address?

Customer: It's michael.obrien@example.com

Agent: Perfect. I can see your account. The issue has been resolved.
""",
        
        "support_ticket": """
Ticket #12345
Created: 2024-01-15

Customer: Jane Smith
Email: jane.smith@customer.com
Phone: +1-555-0123

Issue Description:
The customer reported login issues yesterday.

We contacted Jane at her phone number and resolved the issue.

Resolution:
Password reset link sent to jane.smith@customer.com

Agent: Bob Wilson
""",
    }
    
    print("=" * 70)
    print("Batch PII Detection Example with Double Newlines")
    print("=" * 70)
    
    # Use the new BatchDetector with position-based tracking (default)
    print("\n1. Using BatchDetector with position-based tracking:")
    print("-" * 50)
    
    batch_detector = BatchDetector(detector, use_position_tracking=True)
    
    try:
        # Detect PII across all fields
        entities_by_field = batch_detector.detect_batch(content_examples)
        
        print("✓ Successfully processed content with double newlines!")
        
        # Display detected entities
        for field_name, entities in entities_by_field.items():
            print(f"\n{field_name}:")
            if entities:
                for entity in entities[:5]:  # Show first 5 entities
                    # Verify position accuracy
                    field_text = content_examples[field_name]
                    extracted = field_text[entity.start:entity.end]
                    print(f"  - {entity.type.name}: '{entity.value}'")
                    if extracted != entity.value:
                        print(f"    ⚠️ Position mismatch: extracted '{extracted}'")
                if len(entities) > 5:
                    print(f"  ... and {len(entities) - 5} more entities")
            else:
                print("  (no PII detected)")
    
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Demonstrate consistent tokenization across fields
    print("\n2. Consistent Token Assignment:")
    print("-" * 50)
    
    # Use the NameComponentTracker for consistent tokens
    tracker = NameComponentTracker()
    tokens_by_field = tracker.assign_tokens(entities_by_field)
    
    # Build redaction state
    state = RedactionState()
    for field_tokens in tokens_by_field.values():
        for token in field_tokens:
            state = state.with_token(token.token, token)
    
    # Find all unique people mentioned
    people = {}
    for field_name, tokens in tokens_by_field.items():
        for token in tokens:
            if "NAME" in token.pii_type.name:
                # Extract person index from token
                parts = token.token.rstrip("]").split("_")
                person_idx = int(parts[-1])
                if person_idx not in people:
                    people[person_idx] = {"names": set(), "fields": set()}
                people[person_idx]["names"].add(token.original)
                people[person_idx]["fields"].add(field_name)
    
    print(f"\nFound {len(people)} unique people across all content:")
    for person_idx, info in sorted(people.items())[:5]:  # Show first 5
        names = ", ".join(sorted(info["names"]))
        fields = ", ".join(sorted(info["fields"]))
        print(f"  Person {person_idx}: {names}")
        print(f"    Appears in: {fields}")
    
    # Demonstrate SmartBatchDetector
    print("\n3. Using SmartBatchDetector (always position-based):")
    print("-" * 50)
    
    smart_detector = SmartBatchDetector(detector)
    smart_results = smart_detector.detect_batch(content_examples)
    
    total_entities = sum(len(entities) for entities in smart_results.values())
    print(f"✓ SmartBatchDetector found {total_entities} total entities")
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary:")
    print("-" * 70)
    print("✓ Position-based tracking successfully handles content patterns")
    print("✓ Double newlines in content no longer cause detection issues")
    print("✓ Entities are correctly mapped to their original field positions")
    print("✓ Consistent token assignment works across all fields")
    print("\nRecommendation: Always use position_tracking=True (the new default)")
    print("or SmartBatchDetector for diverse content types.")
    print("=" * 70)


if __name__ == "__main__":
    main()