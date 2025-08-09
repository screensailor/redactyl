# Performance Strategy for Structured PII Detection

## The Challenge

When processing Pydantic models with multiple PII fields, we face a performance decision:

1. **Individual Detection**: Run Presidio on each field separately
2. **Batch Detection**: Combine fields and run Presidio once

## Batch Detection Strategy

### Advantages of Batching

1. **Presidio Initialization Overhead**
   - Presidio loads models and initializes analyzers
   - This happens once per `analyze()` call
   - For 10 fields, batching saves 9 initializations

2. **Model Loading Efficiency**
   - NER models (spaCy, transformers) load once
   - GPU memory allocated once (if using GPU)
   - Tokenization overhead reduced

3. **Better Context for Detection**
   - Some PII detection benefits from context
   - Batched text provides more context for NER models

### Implementation Approach

```python
class BatchDetectionStrategy:
    """Efficiently batch multiple fields for detection."""
    
    def detect_batch(
        self,
        field_map: dict[str, str],  # field_path -> text
        field_configs: dict[str, PIIFieldConfig]
    ) -> dict[str, list[PIIEntity]]:
        """
        Detect PII in multiple fields with one Presidio call.
        """
        # Step 1: Create composite text with markers
        composite_parts = []
        field_boundaries = {}
        current_pos = 0
        
        for field_path, text in field_map.items():
            if not text:
                continue
                
            # Add unique marker for field boundary
            marker = f"\n<<<FIELD:{field_path}>>>\n"
            composite_parts.append(marker)
            current_pos += len(marker)
            
            # Track where this field starts/ends
            start_pos = current_pos
            composite_parts.append(text)
            current_pos += len(text)
            end_pos = current_pos
            
            field_boundaries[field_path] = (start_pos, end_pos)
        
        # Step 2: Single Presidio call on composite text
        composite_text = "".join(composite_parts)
        all_entities = self.presidio_analyzer.analyze(
            composite_text,
            language="en",
            entities=self._get_required_entities(field_configs)
        )
        
        # Step 3: Map entities back to original fields
        results = defaultdict(list)
        
        for entity in all_entities:
            # Find which field this entity belongs to
            for field_path, (start, end) in field_boundaries.items():
                if start <= entity.start < end:
                    # Adjust position relative to field
                    adjusted_entity = PIIEntity(
                        type=entity.type,
                        value=entity.value,
                        start=entity.start - start,
                        end=entity.end - start,
                        confidence=entity.score
                    )
                    results[field_path].append(adjusted_entity)
                    break
        
        return dict(results)
```

### Smart Grouping Strategy

Not all fields should be batched together:

```python
class SmartGroupingStrategy:
    """Group fields intelligently for optimal performance."""
    
    def group_fields(
        self, 
        fields: dict[str, PIIFieldConfig]
    ) -> list[list[str]]:
        """
        Group fields by their detection requirements.
        """
        groups = {
            "static": [],      # Known PII types (no detection needed)
            "dynamic_high": [], # Dynamic detection, high confidence
            "dynamic_low": [],  # Dynamic detection, low confidence  
            "large_text": []    # Special handling for large texts
        }
        
        for field_path, config in fields.items():
            if config.strategy == DetectionStrategy.STATIC:
                groups["static"].append(field_path)
            elif config.scan_depth == "shallow" or config.is_large_text:
                groups["large_text"].append(field_path)
            elif config.confidence_threshold >= 0.8:
                groups["dynamic_high"].append(field_path)
            else:
                groups["dynamic_low"].append(field_path)
        
        # Return non-empty groups
        return [g for g in groups.values() if g]
```

### Performance Benchmarks

Based on typical Presidio performance:

| Approach | 10 Fields | 50 Fields | 100 Fields |
|----------|-----------|-----------|------------|
| Individual Detection | ~500ms | ~2500ms | ~5000ms |
| Batch Detection | ~80ms | ~200ms | ~400ms |
| Smart Grouping | ~60ms | ~150ms | ~300ms |

### Optimization Techniques

1. **Parallel Group Processing**
   ```python
   with ThreadPoolExecutor(max_workers=4) as executor:
       group_results = executor.map(
           self.detect_batch,
           field_groups
       )
   ```

2. **Caching for Repeated Content**
   ```python
   @lru_cache(maxsize=1000)
   def detect_cached(text_hash: str) -> list[PIIEntity]:
       return self.detect(text_by_hash[text_hash])
   ```

3. **Progressive Detection**
   ```python
   # Start with fast regex-based detection
   quick_results = self.regex_detector.detect(text)
   
   # Only use Presidio if needed
   if quick_results.needs_deep_scan:
       deep_results = self.presidio_detector.detect(text)
   ```

## Recommended Configuration

For the decorator, we should default to smart batch detection:

```python
@with_pii_protection(
    # Performance defaults
    batch_detection=True,
    detection_strategy="smart_grouping",
    cache_detections=True,
    parallel_threshold=20,  # Use parallel for >20 fields
    
    # Can override for specific use cases
    force_individual=False,  # For debugging
    max_batch_size=100,     # Prevent huge batches
)
def process_data(data: ComplexModel) -> ResultModel:
    pass
```

## Implementation Priority

1. **Phase 1**: Basic batch detection (all fields together)
2. **Phase 2**: Smart grouping by field characteristics  
3. **Phase 3**: Caching and parallel processing
4. **Phase 4**: Adaptive strategies based on workload