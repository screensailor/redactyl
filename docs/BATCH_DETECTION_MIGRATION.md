# Batch Detection Migration Guide

## Breaking Change: Separator Strategy Update

The `BatchDetector` class has been updated to use **position-based tracking** by default instead of separator-based concatenation. This change was made to better handle content patterns which frequently contain double newlines.

## What Changed

### Before (v0.x)
```python
# Used double newline as separator
batch_detector = BatchDetector(detector, separator="\n\n")
```

**Problem**: Double newlines (`\n\n`) are common in various content types (news articles, chat transcripts, emails), causing incorrect entity detection and position mapping.

### After (v1.0)
```python
# Uses position-based tracking by default
batch_detector = BatchDetector(detector, use_position_tracking=True)  # default

# Or use SmartBatchDetector which always uses position tracking
smart_detector = SmartBatchDetector(detector)
```

**Solution**: Position-based tracking concatenates fields directly without separators, relying on precise position tracking to map entities back to their original fields.

## Migration Steps

### 1. Update Your Code

#### Basic Usage (Recommended)
```python
# Old code
batch_detector = BatchDetector(detector, separator="\n\n")

# New code - just remove the separator argument
batch_detector = BatchDetector(detector)  # position tracking is default
```

#### If You Need Legacy Behavior
```python
# Force legacy boundary marker mode (not recommended)
batch_detector = BatchDetector(detector, use_position_tracking=False)
```

### 2. Use SmartBatchDetector for Best Results
```python
# Always uses position tracking, includes intelligent field grouping
from pii_loop.batch import SmartBatchDetector

smart_detector = SmartBatchDetector(detector)
entities = smart_detector.detect_batch(fields)
```

## Benefits of Position-Based Tracking

1. **No Separator Conflicts**: Content can contain any characters without breaking detection
2. **Better Accuracy**: Entity positions are precisely tracked without separator interference
3. **Improved Performance**: No need to check for separator conflicts
4. **Content Compatible**: Handles double newlines, special characters, and Unicode correctly

## Example: Content Handling with Double Newlines

```python
from pii_loop.batch import BatchDetector
from pii_loop.detectors.presidio import PresidioDetector

detector = PresidioDetector(confidence_threshold=0.7)
batch_detector = BatchDetector(detector)  # Uses position tracking

# Typical content with double newlines
fields = {
    "article": """
    Breaking News: CEO John Smith announced today.
    
    In a press conference, Smith stated that...
    
    Contact: john.smith@company.com
    """,
    "chat": """
    User: Hi, I'm Jane Doe
    
    Agent: Hello Jane! How can I help?
    """
}

# This now works correctly!
entities_by_field = batch_detector.detect_batch(fields)

# Entities are correctly mapped to their fields
for field_path, entities in entities_by_field.items():
    field_text = fields[field_path]
    for entity in entities:
        # Position is accurate
        extracted = field_text[entity.start:entity.end]
        assert extracted == entity.value  # ✓ Always passes
```

## Compatibility Notes

- **Backward Compatible**: Old code continues to work, but we recommend updating
- **No API Changes**: The public API remains the same
- **Better Error Messages**: Clear guidance if boundary markers appear in content

## Testing Your Migration

Run these tests to verify your migration:

```python
def test_migration():
    detector = PresidioDetector()
    
    # Test with problematic content
    fields = {
        "field1": "Contact John at john@example.com\n\nNote: Important",
        "field2": "Email jane@example.com"
    }
    
    # New approach - should work perfectly
    batch_detector = BatchDetector(detector)
    results = batch_detector.detect_batch(fields)
    
    # Verify position accuracy
    for field_path, entities in results.items():
        field_text = fields[field_path]
        for entity in entities:
            extracted = field_text[entity.start:entity.end]
            assert extracted == entity.value
    
    print("✓ Migration successful!")
```

## Questions?

If you encounter any issues during migration:

1. Check that you're using the latest version of redactyl
2. Remove any explicit `separator` arguments from BatchDetector
3. Consider using SmartBatchDetector for optimal results
4. Report issues with specific content examples that fail

## Performance Impact

- **Speed**: Position tracking is slightly faster (no separator checking)
- **Memory**: Negligible difference
- **Accuracy**: Significantly improved for content with natural separators