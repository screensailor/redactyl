# redactyl

**Type-safe PII redaction and unredaction for AI/LLM interactions - protect sensitive data without losing context.**

## Why redactyl?

When using AI language models (LLMs) in production, you need to protect sensitive information. Traditional approaches either block PII entirely (losing context) or use fake data that gets mangled by the AI. 

`redactyl` solves this with a token-based approach that:
- **Preserves context** - AI sees the structure and meaning, not the sensitive data
- **Guarantees reversibility** - Original data is always recoverable
- **Handles real-world complexity** - Names, partial references, hallucinations
- **Integrates seamlessly** - Drop-in solution for existing workflows

## Features

- 🔒 **Token-based redaction** - Replaces PII with tokens like `[NAME_1]` that LLMs preserve exactly
- 🎯 **Intelligent name parsing** - Breaks names into components (title, first, middle, last) using ML
- ⚡ **Batch processing** - Process multiple fields in one call (5-10x faster)
- 🔍 **Hallucination handling** - Gracefully handles when LLMs create tokens that weren't provided
- 🏗️ **Type-safe state management** - Immutable dataclasses prevent corruption
- 🎨 **Pydantic integration** - Decorator-based API for structured data
- 🔄 **Session management** - Accumulate state across conversation turns
- 📊 **Event callbacks** - Hook into the processing pipeline for logging and metrics
- 🚀 **Zero-config setup** - `PIIConfig()` works out of the box with sensible defaults (v0.1.2+)
- 🌐 **Production ready** - Used in production systems processing millions of tokens

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
  - [Why Tokens Instead of Fake Data](#why-tokens-instead-of-fake-data)
  - [How It Works](#how-it-works)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Name Component Parsing](#name-component-parsing)
  - [Pydantic Integration](#pydantic-integration)
  - [Event Callbacks](#event-callbacks)
  - [Batch Processing](#batch-processing)
  - [Session Management](#session-management)
  - [Hallucination Handling](#hallucination-handling)
- [Configuration](#configuration)
- [Entity Types](#entity-types)
- [Performance](#performance)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Installation

```bash
# Basic installation
pip install redactyl

# With GLiNER for enhanced name parsing (recommended)
pip install redactyl[gliner]

# Install spaCy model (required)
python -m spacy download en_core_web_sm
```

### Optional Dependencies

- **GLiNER** (`pip install redactyl[gliner]`) - ML-based name component detection, more accurate than rule-based parsing
- **Large spaCy model** (`python -m spacy download en_core_web_lg`) - Better accuracy for entity detection

## Quick Start

```python
from redactyl.pydantic_integration import PIIConfig

# Simple initialization with sensible defaults (v0.1.2+)
pii = PIIConfig()

@pii.protect
def process_text(text: str) -> str:
    # Text is automatically redacted before processing
    # and unredacted before return
    return f"Processed: {text}"

# Example usage
result = process_text("Contact John at john@example.com")
print(result)  # Original PII is preserved
```

Or using the lower-level API:

```python
from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector

# Initialize and redact
detector = PresidioDetector()
loop = PIILoop(detector)

text = "Contact John at john@example.com"
redacted, state = loop.redact(text)
print(redacted)  # "Contact [PERSON_1] at [EMAIL_1]"

# Process with LLM (it responds with tokens)
llm_response = "I'll email [EMAIL_1] about [PERSON_1]'s request"

# Restore original data
unredacted, _ = loop.unredact(llm_response, state)
print(unredacted)  # "I'll email john@example.com about John's request"
```

## Core Concepts

### Why Tokens Instead of Fake Data?

Some PII tools replace "John Smith" with realistic fake names like "Maria Lynch". This causes problems:
- LLMs naturally vary names: "Maria Lynch" might become "Maria" or "Ms. Lynch" in responses
- The tool can't map these variations back to "John Smith"

Our approach uses tokens like `[NAME_FIRST_1] [NAME_LAST_1]`:
- LLMs preserve these exactly in their responses
- We can always map them back to the original values
- Much more reliable for production use

### How It Works

1. **Detect & Replace**: Finds sensitive data (names, emails, etc.) and replaces them with safe placeholders
2. **Process**: Send the safe text to the AI, which responds using the same placeholders  
3. **Restore**: Put the original sensitive data back into the AI's response

Example: "Email john@example.com" → "Email [EMAIL_1]" → AI responds → Original data restored

## Usage

### Basic Usage

```python
from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector

# Initialize with Presidio detector
detector = PresidioDetector(
    use_gliner_for_names=True,  # Enable GLiNER name parsing
    language="en"  # Language for detection
)
loop = PIILoop(detector=detector, use_name_parsing=True)

# Redact PII
text = "Contact John Smith at john@example.com"
redacted, state = loop.redact(text)
print(redacted)  # "Contact [NAME_FIRST_1] [NAME_LAST_1] at [EMAIL_1]"

# Process with LLM (it might modify tokens)
llm_response = "I'll email [EMAIL_1] about [NAME_FIRST_1]'s request"

# Unredact response
unredacted, issues = loop.unredact(llm_response, state)
print(unredacted)  # "I'll email john@example.com about John's request"
```

### Name Component Parsing

The library intelligently parses names into components using ML (GLiNER) or rule-based parsing:

```python
from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector

# Initialize with name parsing
detector = PresidioDetector(use_gliner_for_names=True)
loop = PIILoop(detector=detector, use_name_parsing=True)

# Complex name example
text = "Dr. Sarah Jane Johnson will meet Prof. John Smith"
redacted, state = loop.redact(text)
print(redacted)
# Output: "[NAME_TITLE_1] [NAME_FIRST_1] [NAME_MIDDLE_1] [NAME_LAST_1] will meet [NAME_TITLE_2] [NAME_FIRST_2] [NAME_LAST_2]"

# Names from the same person share indices
text = "John Smith called. Later, John mentioned..."
redacted, state = loop.redact(text)
# "[NAME_FIRST_1] [NAME_LAST_1] called. Later, [NAME_FIRST_1] mentioned..."
```

### Pydantic Integration

```python
from typing import Annotated
from pydantic import BaseModel
from redactyl.pydantic_integration import PIIConfig, pii_field
from redactyl.types import PIIType

class CustomerEmail(BaseModel):
    sender_name: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
    sender_email: Annotated[str, pii_field(PIIType.EMAIL)]
    subject: str  # Auto-detect PII
    body: Annotated[str, pii_field(detect=True)]  # Explicit detection

# Configure PII protection
config = PIIConfig(detector=detector, batch_detection=True)

@config.protect
async def process_email(email: CustomerEmail) -> str:
    # All PII automatically redacted before this point
    response = await llm.generate(email.model_dump())
    # Response automatically unredacted before return
    return response
```

### Event Callbacks

The callback pattern allows you to hook into the PII processing pipeline for logging, metrics, and custom handling:

#### Available Callbacks

- **`on_gliner_unavailable`** - Called when GLiNER model is not available
- **`on_detection`** - Called when PII entities are detected
- **`on_batch_error`** - Called when batch processing encounters an error
- **`on_hallucination`** - Called when LLM creates tokens that weren't in the original text

#### Example: Custom Logging and Metrics

```python
from redactyl.core import PIILoop
from redactyl.pydantic_integration import PIIConfig
from redactyl.types import PIIEntity
import logging

logger = logging.getLogger(__name__)

# Example metrics collector (could be StatsD, Prometheus, etc.)
class MetricsCollector:
    def increment(self, metric_name: str, value: int = 1) -> None:
        # Your metrics implementation here
        print(f"Metric: {metric_name} = {value}")

metrics = MetricsCollector()

def log_detection(entities: list[PIIEntity]) -> None:
    """Log detected PII entities for audit trail."""
    logger.info(f"Detected {len(entities)} PII entities")
    for entity in entities:
        # Don't log the actual PII value, just the type
        logger.debug(f"  - {entity.type.name} detected")

def track_metrics(entities: list[PIIEntity]) -> None:
    """Send metrics to monitoring system."""
    metrics.increment("pii.entities.detected", len(entities))
    for entity in entities:
        metrics.increment(f"pii.entity_type.{entity.type.name}")

# Configure with callbacks
config = PIIConfig(
    detector=detector,
    on_detection=lambda entities: (
        log_detection(entities),
        track_metrics(entities)
    ),
    on_gliner_unavailable=lambda: logger.warning("GLiNER not available"),
    on_batch_error=lambda exc: logger.error(f"Batch error: {exc}")
)

loop = PIILoop.from_config(config)
```

#### Example: Silencing Warnings

```python
# Silence specific warnings
config = PIIConfig(
    detector=detector,
    on_gliner_unavailable=None,  # Don't warn about missing GLiNER
    on_batch_error=None,  # Don't warn about batch errors
)
```

#### Example: Hallucination Handling

```python
from redactyl.handlers import HallucinationResponse

def handle_hallucinations(issues: list[UnredactionIssue]) -> list[HallucinationResponse]:
    """Custom logic for handling hallucinated tokens."""
    responses = []
    for issue in issues:
        if "EMAIL" in issue.token or "PHONE" in issue.token:
            # Mask sensitive hallucinated tokens
            responses.append(HallucinationResponse.replace("[REDACTED]"))
        else:
            # Keep non-sensitive hallucinated tokens
            responses.append(HallucinationResponse.preserve())
    return responses

config = PIIConfig(
    detector=detector,
    on_hallucination=handle_hallucinations
)

@config.protect
async def process_with_hallucination_handling(text: str) -> str:
    # Hallucinations are automatically handled according to your logic
    return await llm.generate(text)
```

#### Example: Integration with Application Context

```python
class PIIEventTracker:
    """Track PII events in application context."""
    
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.detection_count = 0
        
    def on_detection(self, entities: list[PIIEntity]) -> None:
        self.detection_count += 1
        audit_log.record({
            "event": "pii_detection",
            "user_id": self.user_id,
            "session_id": self.session_id,
            "entity_count": len(entities),
            "entity_types": [e.type.name for e in entities]
        })

# Per-request tracking
tracker = PIIEventTracker(user_id="user123", session_id="sess456")

config = PIIConfig(
    detector=detector,
    on_detection=tracker.on_detection
)
```

### Batch Processing

```python
from redactyl.batch import BatchDetector

batch_detector = BatchDetector(
    detector=detector,
    use_position_tracking=True,  # Recommended for safety
    use_name_parsing=True
)

# Process multiple fields efficiently
fields = {
    "user.name": "John Smith",
    "user.email": "john@example.com", 
    "message": "Please contact me ASAP"
}

# Single detection call for all fields
entities_by_field = batch_detector.detect_batch(fields)
```

### Session Management

```python
from redactyl.session import PIISession

with PIISession(loop) as session:
    # Turn 1
    user1 = "I'm John at john@example.com"
    safe1 = session.redact(user1)
    # → "I'm [NAME_FIRST_1] at [EMAIL_1]"
    
    # Turn 2 (state accumulates)
    user2 = "Also add Jane at jane@example.com"
    safe2 = session.redact(user2)
    # → "Also add [NAME_FIRST_2] at [EMAIL_2]"
    
    # Unredact with accumulated state
    response = "I'll contact [NAME_FIRST_1] and [NAME_FIRST_2]"
    final, issues = session.unredact(response)
    # → "I'll contact John and Jane"
```

### Hallucination Handling

LLMs sometimes create tokens that weren't in the original text. The library handles this gracefully:

```python
from redactyl.handlers import HallucinationHandler, HallucinationResponse

# Example: LLM creates a token that doesn't exist
text = "Contact John about the project"
redacted, state = loop.redact(text)
# → "Contact [PERSON_1] about the project"

# LLM hallucinates a new email token
llm_response = "I'll contact [PERSON_1] at [EMAIL_1]"  # EMAIL_1 doesn't exist!

# Default behavior: preserve the hallucinated token
unredacted, issues = loop.unredact(llm_response, state)
# → "I'll contact John at [EMAIL_1]"
# issues contains UnredactionIssue for EMAIL_1

# Custom handling with fuzzy matching
unredacted, issues = loop.unredact(
    llm_response, 
    state, 
    fuzzy=True  # Try to match similar tokens
)

# Or use the DefaultHallucinationHandler for programmatic control
from redactyl.handlers import DefaultHallucinationHandler
handler = DefaultHallucinationHandler()
unredacted = handler.handle(llm_response, state, issues)
```

## Entity Types

PII (Personal Identifiable Information) types that can be detected:

**Standard Types:**
- `PERSON` - Full names (enhanced with component parsing)
- `EMAIL` - Email addresses
- `PHONE` - Phone numbers  
- `LOCATION` - Addresses, cities, countries
- `CREDIT_CARD` - Credit card numbers
- `SSN` - Social Security Numbers
- `DATE` - Dates and times
- `IP_ADDRESS` - IP addresses
- `URL` - Web URLs

**Name Components (when `parse_name_components=True`):**
- `NAME_TITLE` - Titles (Dr., Mr., Ms.)
- `NAME_FIRST` - First names
- `NAME_MIDDLE` - Middle names
- `NAME_LAST` - Last names

## Configuration

### Detector Options

```python
from redactyl.detectors.presidio import PresidioDetector

detector = PresidioDetector(
    # Core settings
    language="en",  # Detection language
    use_gliner_for_names=True,  # Use GLiNER for name parsing (default: True)
    confidence_threshold=0.7,  # Minimum confidence for detection
    
    # Entity types to detect (None = all)
    supported_entities=None,  # Or ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]
)

# Note: For name component parsing, also enable it in Redactyl:
loop = Redactyl(detector=detector, use_name_parsing=True)
```

### Redaction Options

```python
loop = Redactyl(
    detector=detector,
)

# Fuzzy matching for hallucinated tokens
unredacted, issues = loop.unredact(
    text=llm_response,
    state=state,
    fuzzy=True  # Enable fuzzy matching (default: False)
)
```

## Performance

- **Speed**: Processing 10 fields together is 5-10x faster than one at a time
- **Name parsing**: Adds about 10-15 milliseconds per name with GLiNER
- **Token replacement**: Nearly instant (less than 1 millisecond)
- **Memory usage**: Very light - about 100KB for every 1000 tokens stored

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/redactyl/redactyl.git
cd redactyl

# Install with UV package manager
uv python pin 3.12
uv pip install -e ".[dev]"
uv run python -m spacy download en_core_web_lg
```

### Testing

```bash
# Run all tests
uv run pytest

# With coverage
uv run pytest --cov=pii_loop

# Specific test file
uv run pytest tests/integration/test_batch_real_world.py -v
```

### Code Quality

```bash
# Type checking
uv run pyright src/

# Linting and formatting
uv run ruff check --fix
uv run ruff format
```

### Project Structure

```
redactyl/
├── src/pii_loop/
│   ├── core.py                  # Main Redactyl class
│   ├── types.py                 # Type definitions
│   ├── batch.py                 # Batch detection optimization
│   ├── entity_tracker.py        # Token consistency tracking
│   ├── session.py               # Session management
│   ├── handlers.py              # Hallucination handling
│   ├── callbacks.py             # Event callback system
│   ├── pydantic_integration.py  # Pydantic decorator API
│   └── detectors/
│       ├── base.py              # Detector protocol
│       ├── presidio.py          # Presidio integration
│       ├── gliner_parser.py     # GLiNER name parsing
│       └── smart_mock.py        # Testing detector
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test data
└── examples/
    ├── callback_example.py      # Event callback patterns
    ├── piiconfig_example.py     # Pydantic integration
    └── sky_batch_detection.py   # Batch processing
```

## Troubleshooting

### Model Download Issues

**GLiNER model download on first use:**
```python
# The first time you use name parsing, GLiNER will download its model
# This may take 1-2 minutes depending on your connection
# You'll see output like:
# Fetching 4 files: 100%|██████████| 4/4 [00:00<00:00, 28339.89it/s]
```

**spaCy model not found:**
```bash
# If you get: "Can't find model 'en_core_web_sm'"
python -m spacy download en_core_web_sm
```

### Memory Requirements

- **Minimum**: 1GB RAM for basic operation
- **Recommended**: 2GB RAM for optimal performance
- **Model sizes**:
  - spaCy en_core_web_sm: ~50MB
  - GLiNER model: ~500MB (downloaded on first use)

## Known Limitations

1. **Cross-language support** - Currently optimized for English. Other languages work via Presidio but without name component parsing.

2. **Entity overlap** - When entities overlap (e.g., "John Doe Smith" detected as both "John Doe" and "Doe Smith"), the first detection wins.

3. **First-run latency** - Initial GLiNER model download takes 1-2 minutes. Subsequent runs load from cache.

## Future Enhancements

- **Caching layer** - Cache detection results for repeated content
- **Custom entity types** - Define domain-specific PII types
- **Streaming support** - Process text streams in real-time
- **Cross-document tracking** - Smarter person identity tracking across multiple documents

## Contributing

We use:
- UV package manager (not pip/poetry)
- Pyright for type checking (not mypy)
- Ruff for linting/formatting
- Python 3.12+ features

Please ensure all code passes:
```bash
uv run pyright src/
uv run ruff check --fix
uv run ruff format
uv run pytest
```

## Changelog

### v0.1.2 (2025-01-12)

#### New Features
- **Default PIIConfig**: `PIIConfig()` now works with sensible defaults - automatically creates a PresidioDetector with GLiNER enabled
- **Improved Entity Tracking**: Names and entities are now numbered by document order (reading order) instead of alphabetically, making token indices more intuitive
- **GLiNER Model Caching**: GLiNER models are now cached globally, preventing repeated downloads and significantly speeding up test runs

#### Bug Fixes
- Fixed entity tracking to use document order instead of alphabetical order for token numbering
- Fixed overlapping entity detection in batch mode (e.g., EMAIL overlapping with URL)
- Fixed field processing order to ensure consistent token numbering across nested models

#### Internal Improvements
- Added session-scoped pytest fixtures for better test performance
- Improved test isolation for GLiNER availability testing
- Better handling of name component parsing edge cases

### v0.1.1 (2025-01-05)
- Fixed critical bugs in entity tracking
- Improved name component grouping
- Better handling of partial name references

### v0.1.0 (2025-01-01)
- Initial release
- Core PII redaction and unredaction functionality
- Pydantic integration with decorator API
- Name component parsing with GLiNER support
- Batch processing capabilities
- Session management for conversations
- Comprehensive error handling

## License

MIT License - see LICENSE file for details.