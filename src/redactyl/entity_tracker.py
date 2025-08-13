"""Entity tracking for consistent token assignment across fields."""

from dataclasses import dataclass

from redactyl.types import PIIEntity, PIIType, RedactionToken


@dataclass
class EntityMatch:
    """Represents a match between entities for deduplication."""

    entity1: PIIEntity
    entity2: PIIEntity
    similarity: float  # 0.0 to 1.0
    match_type: str  # "exact", "fuzzy", "partial"


class GlobalEntityTracker:
    """
    Tracks entities globally to ensure consistent token assignment.

    The same entity (e.g., "John Smith") should get the same token
    (e.g., [NAME_1]) across all fields in a batch.
    """

    def __init__(self, fuzzy_threshold: float = 0.9):
        """
        Initialize entity tracker.

        Args:
            fuzzy_threshold: Minimum similarity for fuzzy matching (0.0-1.0)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self._entity_map: dict[tuple[PIIType, str], RedactionToken] = {}
        self._token_counters: dict[str, int] = {}

    def assign_tokens(
        self, entities_by_field: dict[str, list[PIIEntity]]
    ) -> dict[str, list[RedactionToken]]:
        """
        Assign consistent tokens to entities across all fields.

        Args:
            entities_by_field: Mapping of field paths to detected entities

        Returns:
            Mapping of field paths to assigned redaction tokens
        """
        # First pass: collect all unique entities
        unique_entities = self._deduplicate_entities(entities_by_field)

        # Second pass: assign tokens to unique entities
        entity_to_token = self._create_tokens_for_entities(unique_entities)

        # Create value-based index mapping for name consistency
        value_to_index = self._create_value_index_mapping(entity_to_token)

        # Third pass: map tokens back to original field structure
        result: dict[str, list[RedactionToken]] = {}

        for field_path, entities in entities_by_field.items():
            field_tokens: list[RedactionToken] = []

            for entity in entities:
                # Find the token for this entity
                token = self._find_token_for_entity(
                    entity, entity_to_token, value_to_index
                )
                if token:
                    field_tokens.append(token)

            result[field_path] = field_tokens

        return result

    def _deduplicate_entities(
        self, entities_by_field: dict[str, list[PIIEntity]]
    ) -> list[PIIEntity]:
        """Identify unique entities across all fields."""
        unique_entities: list[PIIEntity] = []
        seen_values: dict[tuple[PIIType, str], PIIEntity] = {}

        # Collect all entities, preserving document order (don't sort alphabetically!)
        # The fields should already be in document order from model iteration
        all_entities: list[tuple[str, PIIEntity]] = []
        for field_path in entities_by_field.keys():
            entities = entities_by_field[field_path]
            for entity in entities:
                all_entities.append((field_path, entity))

        # Deduplicate by type and normalized value
        for _, entity in all_entities:
            key = (entity.type, self._normalize_value(entity.value))

            if key not in seen_values:
                # First time seeing this entity
                seen_values[key] = entity
                unique_entities.append(entity)
            else:
                # Check if this is a better version (higher confidence)
                existing = seen_values[key]
                if entity.confidence > existing.confidence:
                    # Replace with higher confidence version
                    idx = unique_entities.index(existing)
                    unique_entities[idx] = entity
                    seen_values[key] = entity

        return unique_entities

    def _normalize_value(self, value: str) -> str:
        """Normalize entity value for comparison."""
        # Simple normalization for now
        # Future: Handle case variations, punctuation, etc.
        return value.strip().lower()

    def _create_value_index_mapping(
        self, entity_to_token: dict[PIIEntity, RedactionToken]
    ) -> dict[str, int]:
        """
        Create a mapping from normalized values to consistent token indices.
        This ensures the same value gets the same index across different PII types.

        For name-related types, we want "John" to always get the same index
        whether it's detected as NAME_FIRST, NAME_MIDDLE, etc.
        Also handles partial references like "Elizabeth Anderson" and "Anderson".
        """
        value_to_index: dict[str, int] = {}

        # Name-related types that should share indices for the same value
        name_types = {
            PIIType.PERSON,
            PIIType.NAME_FIRST,
            PIIType.NAME_MIDDLE,
            PIIType.NAME_LAST,
            PIIType.NAME_TITLE,
        }

        # Collect all name-related entities and their component words
        word_to_indices: dict[str, set[int]] = {}
        
        for entity, token in entity_to_token.items():
            if entity.type in name_types:
                # Split compound names to handle both full and partial references
                words = entity.value.split()
                for word in words:
                    # Normalize each word component
                    normalized_word = word.strip(".,;:'\"").lower()
                    if normalized_word:
                        if normalized_word not in word_to_indices:
                            word_to_indices[normalized_word] = set()
                        word_to_indices[normalized_word].add(token.token_index)
        
        # Assign the minimum index for each word component
        for word, indices in word_to_indices.items():
            value_to_index[word] = min(indices)
        
        # Also map full normalized values
        for entity, token in entity_to_token.items():
            if entity.type in name_types:
                normalized = self._normalize_value(entity.value)
                if normalized not in value_to_index:
                    value_to_index[normalized] = token.token_index
                else:
                    # Use the minimum index for consistency
                    value_to_index[normalized] = min(
                        value_to_index[normalized], token.token_index
                    )

        return value_to_index

    def _create_tokens_for_entities(
        self, entities: list[PIIEntity]
    ) -> dict[PIIEntity, RedactionToken]:
        """Create redaction tokens for unique entities.

        Non-name entities are numbered per type. Name-related entities
        (PERSON/NAME_*) are numbered together based on document order
        of their first appearance so components receive
        consistent indices across types preserving the reading order.
        """
        entity_to_token: dict[PIIEntity, RedactionToken] = {}

        name_types = {
            PIIType.PERSON,
            PIIType.NAME_FIRST,
            PIIType.NAME_MIDDLE,
            PIIType.NAME_LAST,
            PIIType.NAME_TITLE,
        }

        # Group entities by type for separate numbering
        entities_by_type: dict[PIIType, list[PIIEntity]] = {}

        for entity in entities:
            entities_by_type.setdefault(entity.type, []).append(entity)

        # Process name types with separate counters for each subtype
        for pii_type in name_types:
            if pii_type not in entities_by_type:
                continue
                
            type_entities = entities_by_type[pii_type]
            
            # Build ordering based on unique values in document order
            def norm(e: PIIEntity) -> str:
                return e.value.strip().lower()
            
            unique_values: list[str] = []
            for e in type_entities:  # Keep original order from deduplication
                v = norm(e)
                if v not in unique_values:
                    unique_values.append(v)
            
            value_to_index = {v: i + 1 for i, v in enumerate(unique_values)}
            
            for e in type_entities:
                idx = value_to_index[norm(e)]
                entity_to_token[e] = RedactionToken(
                    original=e.value,
                    pii_type=e.type,
                    token_index=idx,
                    entity=e,
                )

        # Assign tokens with consistent numbering per non-name type
        for pii_type, type_entities in entities_by_type.items():
            if pii_type in name_types:
                continue  # Already processed above
            # Sort by value for consistent ordering
            sorted_entities = sorted(type_entities, key=lambda e: e.value)

            for idx, entity in enumerate(sorted_entities, 1):
                token = RedactionToken(
                    original=entity.value,
                    pii_type=entity.type,
                    token_index=idx,
                    entity=entity,
                )
                entity_to_token[entity] = token

        return entity_to_token

    def _find_token_for_entity(
        self,
        entity: PIIEntity,
        entity_to_token: dict[PIIEntity, RedactionToken],
        value_to_index: dict[str, int] | None = None,
    ) -> RedactionToken | None:
        """Find the token assigned to an entity or equivalent."""
        # For name types, use consistent value-based indexing if available
        name_types = {
            PIIType.PERSON,
            PIIType.NAME_FIRST,
            PIIType.NAME_MIDDLE,
            PIIType.NAME_LAST,
            PIIType.NAME_TITLE,
        }

        normalized = self._normalize_value(entity.value)

        # If this is a name-related entity and we have a value index, use it
        if value_to_index and entity.type in name_types:
            # First try the full normalized value
            if normalized in value_to_index:
                consistent_index = value_to_index[normalized]
                return RedactionToken(
                    original=entity.value,
                    pii_type=entity.type,
                    token_index=consistent_index,
                    entity=entity,
                )
            
            # For partial references, check individual words
            words = entity.value.split()
            if len(words) == 1:
                # Single word - check normalized version
                word_normalized = words[0].strip(".,;:'\"").lower()
                if word_normalized in value_to_index:
                    consistent_index = value_to_index[word_normalized]
                    return RedactionToken(
                        original=entity.value,
                        pii_type=entity.type,
                        token_index=consistent_index,
                        entity=entity,
                    )

        # For non-name entities or when no value index, try exact match first
        if entity in entity_to_token:
            return entity_to_token[entity]

        # Otherwise, try normalized value match with same type
        for mapped_entity, token in entity_to_token.items():
            if (
                mapped_entity.type == entity.type
                and self._normalize_value(mapped_entity.value) == normalized
            ):
                # Return token but with this entity's original value
                return RedactionToken(
                    original=entity.value,  # Keep original casing
                    pii_type=token.pii_type,
                    token_index=token.token_index,
                    entity=entity,
                )

        return None


class NameComponentTracker(GlobalEntityTracker):
    """
    Enhanced tracker that handles name component relationships.

    Ensures that name components from the same person get related tokens:
    - "Dr. John Smith" → [TITLE_1] [FIRST_NAME_1] [LAST_NAME_1]
    - "John" (same person) → [FIRST_NAME_1]
    """

    def __init__(self, fuzzy_threshold: float = 0.9):
        super().__init__(fuzzy_threshold)
        self._name_groups: dict[str, list[PIIEntity]] = {}

    def assign_tokens(
        self, entities_by_field: dict[str, list[PIIEntity]]
    ) -> dict[str, list[RedactionToken]]:
        """
        Assign tokens with special handling for name components.
        """
        # First, identify name component groups
        self._group_name_components(entities_by_field)

        # Then use parent logic with grouped entities
        return super().assign_tokens(entities_by_field)

    def _group_name_components(
        self, entities_by_field: dict[str, list[PIIEntity]]
    ) -> None:
        """Group related name components together."""
        # Collect all name-related entities
        name_entities: list[tuple[str, PIIEntity]] = []

        for field_path, entities in entities_by_field.items():
            for entity in entities:
                if entity.type in {
                    PIIType.PERSON,
                    PIIType.NAME_FIRST,
                    PIIType.NAME_MIDDLE,
                    PIIType.NAME_LAST,
                    PIIType.NAME_TITLE,
                }:
                    name_entities.append((field_path, entity))

        # Group by proximity and value overlap
        # This is a simplified version - real implementation would be more sophisticated
        groups: list[list[PIIEntity]] = []

        for _, entity in name_entities:
            # Find existing group this entity belongs to
            added = False
            for group in groups:
                if self._entities_related(entity, group):
                    group.append(entity)
                    added = True
                    break

            if not added:
                # Start new group
                groups.append([entity])

        # Store groups for token assignment
        for idx, group in enumerate(groups):
            group_id = f"name_group_{idx}"
            self._name_groups[group_id] = group

    def _entities_related(self, entity: PIIEntity, group: list[PIIEntity]) -> bool:
        """Check if an entity is related to a group of entities."""
        # Normalize and split entity value into words
        entity_words = set(word.strip(".,;:'\"").lower() 
                          for word in entity.value.split() 
                          if word.strip(".,;:'\""))

        for group_entity in group:
            # Normalize and split group entity value into words
            group_words = set(word.strip(".,;:'\"").lower() 
                            for word in group_entity.value.split() 
                            if word.strip(".,;:'\""))
            
            # Check if any words overlap
            if entity_words & group_words:  # Intersection
                return True

        return False

    def _create_tokens_for_entities(
        self, entities: list[PIIEntity]
    ) -> dict[PIIEntity, RedactionToken]:
        """Create tokens with consistent numbering for name groups."""
        entity_to_token = super()._create_tokens_for_entities(entities)

        # Build a mapping of values to their assigned indices
        value_to_min_index: dict[str, int] = {}
        
        for entity, token in entity_to_token.items():
            # Normalize the value
            normalized = entity.value.lower().strip()
            
            # Track minimum index for each value
            if normalized not in value_to_min_index:
                value_to_min_index[normalized] = token.token_index
            else:
                value_to_min_index[normalized] = min(
                    value_to_min_index[normalized], token.token_index
                )
            
            # Also track individual words for partial matches
            words = normalized.split()
            for word in words:
                word_clean = word.strip(".,;:'\"")
                if word_clean:
                    if word_clean not in value_to_min_index:
                        value_to_min_index[word_clean] = token.token_index
                    else:
                        value_to_min_index[word_clean] = min(
                            value_to_min_index[word_clean], token.token_index
                        )
        
        # Now update tokens to use consistent indices based on value matching
        for entity, token in list(entity_to_token.items()):
            normalized = entity.value.lower().strip()
            
            # Check if this value or any of its words have a lower index
            min_index = token.token_index
            
            # Check full value
            if normalized in value_to_min_index:
                min_index = min(min_index, value_to_min_index[normalized])
            
            # Check individual words
            words = normalized.split()
            for word in words:
                word_clean = word.strip(".,;:'\"")
                if word_clean and word_clean in value_to_min_index:
                    min_index = min(min_index, value_to_min_index[word_clean])
            
            # Update token if we found a lower index
            if min_index < token.token_index:
                entity_to_token[entity] = RedactionToken(
                    original=token.original,
                    pii_type=token.pii_type,
                    token_index=min_index,
                    entity=token.entity,
                )

        return entity_to_token
