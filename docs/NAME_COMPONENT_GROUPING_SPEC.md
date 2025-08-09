# Name Component Index Grouping Specification

## Problem Statement

When parsing names into components (FIRST_NAME, MIDDLE_NAME, LAST_NAME, TITLE), we need consistent indexing so components of the same person share the same index.

## Current Behavior (INCORRECT)

```python
"John Smith" → [NAME_FIRST_2] [NAME_LAST_1]  # Different indices!
"Jane" then "Jane" → [NAME_FIRST_1] then [NAME_FIRST_2]  # Same person, different indices
```

## Required Behavior (CORRECT)

```python
"John Smith" → [NAME_FIRST_1] [NAME_LAST_1]  # Same index for same person
"Jane Doe" then "Jane" → [NAME_FIRST_1] [NAME_LAST_1] then [NAME_FIRST_1]  # Reuses index
```

## Implementation Rules

### Rule 1: Components from Same Span Share Index
When a PERSON entity is parsed into components, ALL components get the SAME index:
- "Dr. Jane Smith" detected as single span → `[NAME_TITLE_1] [NAME_FIRST_1] [NAME_LAST_1]`
- "Daniel Clement Dennett" → `[NAME_FIRST_1] [NAME_MIDDLE_1] [NAME_LAST_1]`

### Rule 2: Identity Tracking Within Document
Within a single document/email, assume same first name = same person:

1. **Full name creates identity**: "John Smith" → Person 1
2. **Partial match reuses identity**: Later "John" → Still Person 1
3. **Different last name = different person**: "John Doe" → Person 2

### Rule 3: Order Independence
The order of appearance doesn't matter:
- "John" then "John Smith" → Both are Person 1
- "John Smith" then "John" → Both are Person 1

## Examples

### Example 1: Email Pattern
```
Input: "Hi, I'm John. ... Sincerely, John Smith"
Output: "Hi, I'm [NAME_FIRST_1]. ... Sincerely, [NAME_FIRST_1] [NAME_LAST_1]"
```

### Example 2: Multiple People
```
Input: "John Smith and Jane Doe met with John from accounting"
Output: "[NAME_FIRST_1] [NAME_LAST_1] and [NAME_FIRST_2] [NAME_LAST_2] met with [NAME_FIRST_1] from accounting"
```
(Note: "John from accounting" assumed to be John Smith unless different last name given)

### Example 3: Same First Name, Different People
```
Input: "John Smith and John Doe are different people"
Output: "[NAME_FIRST_1] [NAME_LAST_1] and [NAME_FIRST_2] [NAME_LAST_2] are different people"
```

## Implementation Approach

1. **Track Person Identities**: Maintain a registry of detected persons
2. **Key by Full Name When Available**: "john_smith" as person key
3. **Map Partials to Full**: Track that "john" belongs to "john_smith"
4. **Assign Indices by Person**: All components of Person 1 get index 1

## Test Cases to Verify

```python
# Test 1: Components share index
assert "John Smith" → "[NAME_FIRST_1] [NAME_LAST_1]"

# Test 2: Partial reuses index  
assert "John Smith ... John" → "[NAME_FIRST_1] [NAME_LAST_1] ... [NAME_FIRST_1]"

# Test 3: Different people with same first name
assert "John Smith and John Doe" → "[NAME_FIRST_1] [NAME_LAST_1] and [NAME_FIRST_2] [NAME_LAST_2]"

# Test 4: Complex name components grouped
assert "Dr. Jane Elizabeth Smith" → "[NAME_TITLE_1] [NAME_FIRST_1] [NAME_MIDDLE_1] [NAME_LAST_1]"
```

## Files to Modify

1. `src/pii_loop/entity_tracker.py` - Main logic for person grouping
2. `src/pii_loop/core.py` - Integration with Redactyl
3. Tests - Update to verify correct behavior

## Success Criteria

All name components from the same person must share the same index number, enabling proper tracking of which first name goes with which last name.