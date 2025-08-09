# Dynamic PII Detection Architecture for redactyl

## Overview

This document describes the architectural extension to support dynamic PII detection in the redactyl library. The design addresses the critical use case where fields may contain PII but we don't know ahead of time what type or if any PII is present.

## Core Design Principles

1. **Ergonomic API First** - Simple cases stay simple, complex cases are possible
2. **Type Safety** - Leverage Python's type system for compile-time guarantees
3. **Performance Conscious** - Fast path for known PII, comprehensive scan only when needed
4. **Composable** - Mix static and dynamic strategies in the same model
5. **Progressive Enhancement** - Existing code continues to work

## Architecture Components

### Detection Strategies

```python
class DetectionStrategy(Enum):
    STATIC = auto()   # Field is always PII of known type (fastest)
    DYNAMIC = auto()  # Field might contain PII, needs scanning (slower)
    HYBRID = auto()   # Field has known type but might contain others
```

### Field Metadata System

The core innovation is enriching field annotations with detection metadata:

```python
@dataclass
class PIIFieldMetadata:
    strategy: DetectionStrategy = DetectionStrategy.STATIC
    types: list[PIIType] | None = None
    confidence_threshold: float = 0.7
    scan_depth: Literal["shallow", "deep"] = "shallow"
```

### Type Aliases for Ergonomics

```python
# Simple static PII (most common case)
email: Annotated[str, pii_field(PIIType.EMAIL)]

# Dynamic detection
notes: Annotated[str, pii_field(strategy=DetectionStrategy.DYNAMIC)]

# Hybrid with hints
bio: Annotated[str, pii_field(
    PIIType.EMAIL, PIIType.PHONE,
    strategy=DetectionStrategy.HYBRID
)]
```

## Integration Patterns

### 1. Microsoft Presidio Integration

Presidio is the most mature open-source PII detection framework:

```python
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

class PresidioDetector(EnhancedPIIDetector):
    def __init__(self):
        # Use spaCy for better NER
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]
        })
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
    
    def detect_dynamic(self, text: str, context: DetectionContext):
        # Use Presidio's full detection capabilities
        results = self.analyzer.analyze(
            text=text,
            language="en",
            score_threshold=context.field_metadata.confidence_threshold
        )
        return self._convert_results(results)
```

**Advantages:**
- Production-ready with extensive language support
- Pluggable recognizers for custom PII types
- Built-in confidence scoring
- Active maintenance by Microsoft

### 2. spaCy + Custom Rules

For more control over NER and custom patterns:

```python
import spacy
from spacy.matcher import Matcher

class SpacyDetector(EnhancedPIIDetector):
    def __init__(self):
        self.nlp = spacy.load("en_core_web_trf")  # Transformer model
        self.matcher = Matcher(self.nlp.vocab)
        self._add_custom_patterns()
    
    def detect_dynamic(self, text: str, context: DetectionContext):
        doc = self.nlp(text)
        
        # NER-based detection
        entities = []
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG", "GPE"]:
                entities.append(self._create_entity(ent))
        
        # Pattern-based detection
        matches = self.matcher(doc)
        for match_id, start, end in matches:
            entities.append(self._create_match_entity(doc[start:end]))
        
        return entities
```

### 3. Transformer-Based Detection

For state-of-the-art accuracy using models like BERT:

```python
from transformers import pipeline

class TransformerDetector(EnhancedPIIDetector):
    def __init__(self):
        # Use a fine-tuned model for PII detection
        self.pipeline = pipeline(
            "token-classification",
            model="dslim/bert-base-NER",
            aggregation_strategy="simple"
        )
    
    def detect_dynamic(self, text: str, context: DetectionContext):
        # Get predictions
        predictions = self.pipeline(text)
        
        # Convert to our entity format
        entities = []
        for pred in predictions:
            if pred['score'] >= context.field_metadata.confidence_threshold:
                entities.append(PIIEntity(
                    type=self._map_label(pred['entity_group']),
                    value=pred['word'],
                    start=pred['start'],
                    end=pred['end'],
                    confidence=pred['score']
                ))
        
        return entities
```

### 4. Hybrid Approach with Caching

For production systems with performance requirements:

```python
from functools import lru_cache
import hashlib

class CachedHybridDetector(EnhancedPIIDetector):
    def __init__(self):
        self.regex_detector = RegexDetector()  # Fast
        self.ml_detector = PresidioDetector()  # Accurate
        self._cache = {}
    
    def detect_with_context(self, text: str, context: DetectionContext):
        # Cache key includes strategy and confidence threshold
        cache_key = self._compute_cache_key(text, context)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if context.field_metadata.scan_depth == "shallow":
            # Fast regex-based scan
            entities = self.regex_detector.detect(text)
        else:
            # Full ML-based scan
            entities = self.ml_detector.detect_dynamic(text, context)
        
        self._cache[cache_key] = entities
        return entities
```

## Performance Considerations

### Detection Strategy Performance Impact

| Strategy | Relative Speed | Use Case |
|----------|---------------|----------|
| STATIC | 1x (baseline) | Known PII fields (email, phone) |
| DYNAMIC (shallow) | 5-10x slower | User-generated content |
| DYNAMIC (deep) | 20-50x slower | Complex documents |
| HYBRID | 2-5x slower | Mixed content fields |

### Optimization Techniques

1. **Batch Processing** - Process multiple fields together
2. **Async Detection** - Use async/await for I/O-bound detectors
3. **Model Caching** - Load models once, reuse across requests
4. **Result Caching** - Cache detection results for repeated content
5. **Progressive Detection** - Start with fast detectors, escalate if needed

## Security Considerations

1. **Confidence Thresholds** - Set appropriately to balance false positives/negatives
2. **Context Isolation** - Don't leak information between fields/models
3. **Detector Sandboxing** - Run untrusted detectors in isolated environments
4. **Audit Logging** - Log what was detected and redacted for compliance

## Migration Guide

### From Simple Annotations

```python
# Before
class User(BaseModel):
    email: str  # Manual detection needed
    bio: str    # Manual detection needed

# After
class User(BaseModel):
    email: Annotated[str, pii_field(PIIType.EMAIL)]
    bio: Annotated[str, pii_field(strategy=DetectionStrategy.DYNAMIC)]
```

### From Custom Detection Logic

```python
# Before
def process_user(user: User):
    if contains_email(user.email):
        user.email = redact_email(user.email)
    # Complex detection logic for bio...

# After
def process_user(user: User):
    redacted_data, state = pii_loop.redact_model(user)
    # All detection handled by framework
```

## Future Enhancements

1. **Contextual Detection** - Use surrounding fields to improve accuracy
2. **Multi-lingual Support** - Detect PII in multiple languages
3. **Custom PII Types** - Plugin system for domain-specific PII
4. **Streaming Detection** - Process large documents in chunks
5. **Reversible Tokenization** - Format-preserving encryption for some fields

## Conclusion

The dynamic PII detection architecture extends redactyl to handle real-world scenarios where PII presence is uncertain. By maintaining a clean, type-safe API while enabling sophisticated detection strategies, the system provides both ease of use and production-ready capabilities.