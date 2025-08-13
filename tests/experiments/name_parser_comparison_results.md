# Name Parser Library Comparison for Redactyl

## Executive Summary

**Recommendation: Use `nameparser` library**

After comprehensive testing of both `nameparser` and `probablepeople` libraries on 15 diverse person names, `nameparser` emerges as the clear choice for redactyl's use case.

## Key Findings

### Performance
- **nameparser**: Average 0.039ms per name (2.9x faster)
- **probablepeople**: Average 0.114ms per name

### API Simplicity
```python
# nameparser - Simple and intuitive
from nameparser import HumanName
name = HumanName("Dr. Jane Smith")
first = name.first  # "Jane"
last = name.last    # "Smith"
title = name.title  # "Dr."

# probablepeople - More complex
import probablepeople as pp
parsed, label_type = pp.tag("Dr. Jane Smith")
first = parsed.get('GivenName', '')  # "Jane"
last = parsed.get('Surname', '')     # "Smith"
title = parsed.get('PrefixOther', '') # "Dr."
```

### Accuracy Comparison

Both libraries performed well on the test set:

| Name Type | Example | nameparser | probablepeople | Notes |
|-----------|---------|------------|----------------|-------|
| Simple | "John Doe" | ✓ | ✓ | Both perfect |
| With Title | "Dr. Jane Smith" | ✓ | ✓ | Both handle well |
| With Suffix | "Robert Johnson Jr." | ✓ | ✓ | Both identify correctly |
| Middle Name | "John F. Kennedy" | ✓ | ✓ | Both parse middle initial |
| Hyphenated | "Mary-Kate Olsen" | ✓ | ✓ | Both handle hyphens |
| Apostrophe | "Patrick O'Brien" | ✓ | ✓ | Both preserve apostrophe |
| Single Name | "Madonna" | ✓ | ✓ | Both recognize mononym |
| Non-Western | "Xi Jinping" | ✓ | ✓ | Both parse (though may misinterpret order) |
| Complex Title | "Prof. Dr. Hans Mueller" | ✓ | ⚠️ | probablepeople misclassifies as Corporation |

### Edge Cases

probablepeople incorrectly classified two names:
1. "François Hollande" → Corporation (likely due to accent)
2. "Prof. Dr. Hans Mueller" → Corporation (multiple titles confused it)

## Why nameparser for Redactyl?

1. **Speed**: 2.9x faster on average
2. **Simplicity**: Direct attribute access vs dictionary lookups
3. **Reliability**: Fewer misclassifications on edge cases
4. **Context**: Since spaCy already identifies PERSON entities, we don't need probablepeople's entity type detection
5. **Integration**: Cleaner mapping to PIIEntity objects

## Implementation Example

```python
from nameparser import HumanName

def parse_person_name(name_text: str) -> dict:
    """Parse a person name identified by spaCy."""
    parsed = HumanName(name_text)
    return {
        'first': parsed.first,
        'middle': parsed.middle,
        'last': parsed.last,
        'title': parsed.title,
        'suffix': parsed.suffix,
        'full': name_text
    }
```

## Test Coverage

The comparison test (`test_name_parser_comparison.py`) includes:
- 15 diverse test names
- Performance benchmarking
- API ease-of-use comparison
- Edge case handling
- Full pytest test suite

All tests pass successfully, confirming both libraries work but nameparser is optimal for redactyl's needs.