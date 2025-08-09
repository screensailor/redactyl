#!/usr/bin/env python3
"""
Example demonstrating GLiNER as an optional dependency.

GLiNER provides enhanced name parsing capabilities but is optional.
Install with: pip install redactyl[gliner]

This example shows how the library gracefully handles both cases.
"""

import warnings
from redactyl.detectors.presidio import PresidioDetector
from redactyl.detectors.gliner_parser import GlinerNameParser


def test_gliner_availability():
    """Check if GLiNER is available."""
    print("=" * 60)
    print("Testing GLiNER Availability")
    print("=" * 60)
    
    # Test GlinerNameParser directly
    parser = GlinerNameParser()
    
    if parser.is_available:
        print("✓ GLiNER is installed and available")
        print(f"  Model: {parser.model_name}")
    else:
        print("✗ GLiNER is not available")
        print("  Install with: pip install redactyl[gliner]")
        print("  Falling back to nameparser for name component detection")
    
    print()
    return parser.is_available


def demo_name_detection(use_gliner: bool = True):
    """Demonstrate name detection with and without GLiNER."""
    print("=" * 60)
    print(f"Name Detection Demo (use_gliner={use_gliner})")
    print("=" * 60)
    
    # Sample text with names
    text = """
    Dr. Jane Smith called yesterday about the meeting.
    John Michael Doe will also attend.
    Ms. Emily Chen-Martinez confirmed her participation.
    """
    
    # Create detector
    print(f"\nCreating PresidioDetector with use_gliner_for_names={use_gliner}")
    
    # Suppress warnings for cleaner output
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        detector = PresidioDetector(use_gliner_for_names=use_gliner)
    
    # Check what parser is being used
    if detector._gliner_parser is not None and detector._gliner_parser.is_available:
        print("→ Using GLiNER for name parsing")
    else:
        print("→ Using nameparser for name parsing")
    
    # Detect with name parsing
    print("\nDetecting PII with name component parsing...")
    entities = detector.detect_with_name_parsing(text)
    
    # Group by type for display
    by_type = {}
    for entity in entities:
        type_name = entity.type.value
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(entity)
    
    # Display results
    print("\nDetected entities:")
    for type_name in sorted(by_type.keys()):
        print(f"\n  {type_name}:")
        for entity in by_type[type_name]:
            print(f"    - '{entity.value}' (confidence: {entity.confidence:.2f})")


def main():
    """Run the demonstration."""
    print("\n" + "=" * 60)
    print("Redactyl: GLiNER Optional Dependency Example")
    print("=" * 60)
    
    # Check GLiNER availability
    has_gliner = test_gliner_availability()
    
    # Demo with GLiNER (if available)
    if has_gliner:
        print("\n")
        demo_name_detection(use_gliner=True)
    
    # Demo without GLiNER (always available)
    print("\n")
    demo_name_detection(use_gliner=False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print("\nThe redactyl library works with or without GLiNER:")
    print("• With GLiNER: Enhanced name component detection using ML model")
    print("• Without GLiNER: Falls back to rule-based nameparser")
    print("\nBoth approaches provide name component parsing capabilities!")
    
    if not has_gliner:
        print("\nTo enable GLiNER support:")
        print("  pip install redactyl[gliner]")


if __name__ == "__main__":
    main()