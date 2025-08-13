"""Entity tracking for consistent token assignment across fields."""

import threading
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
        # Persistent mapping of exact (type, normalized_value) -> token
        self._entity_map: dict[tuple[PIIType, str], RedactionToken] = {}
        # Persistent counters per type name and for names under key 'NAME'
        self._token_counters: dict[str, int] = {}
        # Persistent names map: full normalized values and component words -> shared index
        self._name_index_by_value: dict[str, int] = {}
        # Persistent mapping from last-name (normalized) -> first-name (normalized)
        # Established from authoritative "First Last" phrases.
        self._last_to_first: dict[str, str] = {}
        # Simple lock for concurrent access safety
        self._lock = threading.Lock()

    def assign_tokens(self, entities_by_field: dict[str, list[PIIEntity]]) -> dict[str, list[RedactionToken]]:
        """
        Assign consistent tokens to entities across all fields.

        Args:
            entities_by_field: Mapping of field paths to detected entities

        Returns:
            Mapping of field paths to assigned redaction tokens
        """
        # Pre-scan: Build authoritative mapping from full-name occurrences
        with self._lock:
            for _, entities in entities_by_field.items():
                recent_first: PIIEntity | None = None
                for e in entities:
                    if e.type == PIIType.NAME_FIRST:
                        recent_first = e
                    elif e.type == PIIType.NAME_LAST:
                        if recent_first is not None:
                            gap = e.start - recent_first.end
                            if 0 <= gap <= 2:
                                first_norm = self._normalize_value(recent_first.value)
                                last_norm = self._normalize_value(e.value)
                                # Only set if not already mapped to avoid flip-flops
                                self._last_to_first.setdefault(last_norm, first_norm)
                        # End of a "first ... last" phrase
                        recent_first = None
                    elif e.type in {PIIType.NAME_MIDDLE, PIIType.NAME_TITLE}:
                        # Keep recent_first
                        pass
                    else:
                        recent_first = None

        # First pass: collect all unique entities
        unique_entities = self._deduplicate_entities(entities_by_field)

        # Second pass: assign or reuse tokens persistently
        entity_to_token = self._ensure_persistent_tokens(unique_entities)

        # Value-based index mapping for names from persistent map
        value_to_index = {**self._name_index_by_value}

        # Third pass: map tokens back to original field structure
        result: dict[str, list[RedactionToken]] = {}

        for field_path, entities in entities_by_field.items():
            field_tokens: list[RedactionToken] = []

            for entity in entities:
                # Find the token for this entity
                token = self._find_token_for_entity(entity, entity_to_token, value_to_index)
                if token:
                    field_tokens.append(token)

            result[field_path] = field_tokens

        return result

    def _deduplicate_entities(self, entities_by_field: dict[str, list[PIIEntity]]) -> list[PIIEntity]:
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

    def _create_value_index_mapping(self, entity_to_token: dict[PIIEntity, RedactionToken]) -> dict[str, int]:
        """
        Create a mapping from normalized values to consistent token indices.
        Legacy compatibility - now returns persistent map.
        """
        return dict(self._name_index_by_value)

    def _create_tokens_for_entities(self, entities: list[PIIEntity]) -> dict[PIIEntity, RedactionToken]:
        """Create redaction tokens for unique entities.

        Legacy path now uses persistent assignment.
        """
        return self._ensure_persistent_tokens(entities)

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
            if mapped_entity.type == entity.type and self._normalize_value(mapped_entity.value) == normalized:
                # Return token but with this entity's original value
                return RedactionToken(
                    original=entity.value,  # Keep original casing
                    pii_type=token.pii_type,
                    token_index=token.token_index,
                    entity=entity,
                )

        return None

    def _ensure_persistent_tokens(self, entities: list[PIIEntity]) -> dict[PIIEntity, RedactionToken]:
        """Assign or reuse tokens persistently across calls."""
        entity_to_token: dict[PIIEntity, RedactionToken] = {}
        name_types = {
            PIIType.PERSON,
            PIIType.NAME_FIRST,
            PIIType.NAME_MIDDLE,
            PIIType.NAME_LAST,
            PIIType.NAME_TITLE,
        }

        def norm(s: str) -> str:
            return s.strip().lower()

        with self._lock:
            if "NAME" not in self._token_counters:
                self._token_counters["NAME"] = 0
            # Track last name component to group contiguous mentions
            last_name_entity: PIIEntity | None = None

            for entity in entities:
                normalized = norm(entity.value)

                if entity.type in name_types:
                    # Check if we've seen this name value before
                    idx = self._name_index_by_value.get(normalized)

                    # If not, check if any component word has been seen
                    if idx is None:
                        for word in normalized.split():
                            w = word.strip(".,;:'\"")
                            if w and w in self._name_index_by_value:
                                idx = self._name_index_by_value[w]
                                break

                    # If still no index, consider contiguous component grouping
                    # Reuse previous name index when components are adjacent (same phrase)
                    if idx is None and last_name_entity is not None:
                        gap = entity.start - last_name_entity.end
                        if 0 <= gap <= 2:
                            prev_token = entity_to_token.get(last_name_entity)
                            if prev_token is not None:
                                idx = prev_token.token_index

                    # If still no index and we saw a full-name mapping last->first,
                    # tie this last name to that first name's index.
                    if idx is None and entity.type == PIIType.NAME_LAST:
                        mapped_first = self._last_to_first.get(normalized)
                        if mapped_first is not None:
                            # Reuse first's index if seen; otherwise allocate and register both
                            idx = self._name_index_by_value.get(mapped_first)
                            if idx is None:
                                self._token_counters["NAME"] += 1
                                idx = self._token_counters["NAME"]
                                self._register_name_value_indices(mapped_first, idx)

                    # If still no index, create a new one
                    if idx is None:
                        self._token_counters["NAME"] += 1
                        idx = self._token_counters["NAME"]

                    # Register this value and its component words
                    self._register_name_value_indices(normalized, idx)

                    token = RedactionToken(
                        original=entity.value,
                        pii_type=entity.type,
                        token_index=idx,
                        entity=entity,
                    )
                    entity_to_token[entity] = token
                    self._entity_map[(entity.type, normalized)] = token
                    # Continue current name group
                    last_name_entity = entity

                else:
                    # Non-name entities
                    key = (entity.type, normalized)
                    if key in self._entity_map:
                        # Reuse existing token
                        base = self._entity_map[key]
                        token = RedactionToken(
                            original=entity.value,
                            pii_type=base.pii_type,
                            token_index=base.token_index,
                            entity=entity,
                        )
                        entity_to_token[entity] = token
                    else:
                        # Create new token with next index
                        tname = entity.type.name
                        self._token_counters[tname] = self._token_counters.get(tname, 0) + 1
                        idx = self._token_counters[tname]

                        token = RedactionToken(
                            original=entity.value,
                            pii_type=entity.type,
                            token_index=idx,
                            entity=entity,
                        )
                        entity_to_token[entity] = token
                        self._entity_map[key] = token
                    # Reset current name group on non-name
                    last_name_entity = None

        return entity_to_token

    def _register_name_value_indices(self, normalized_value: str, idx: int) -> None:
        """Register a name value and its component words with the given index."""
        if normalized_value and normalized_value not in self._name_index_by_value:
            self._name_index_by_value[normalized_value] = idx

        # Also register component words
        for word in normalized_value.split():
            w = word.strip(".,;:'\"")
            if w and w not in self._name_index_by_value:
                self._name_index_by_value[w] = idx


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

    def assign_tokens(self, entities_by_field: dict[str, list[PIIEntity]]) -> dict[str, list[RedactionToken]]:
        """
        Assign tokens with special handling for name components.
        """
        # First, identify name component groups
        self._group_name_components(entities_by_field)

        # Then use parent logic with grouped entities
        return super().assign_tokens(entities_by_field)

    def _group_name_components(self, entities_by_field: dict[str, list[PIIEntity]]) -> None:
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
        entity_words = set(word.strip(".,;:'\"").lower() for word in entity.value.split() if word.strip(".,;:'\""))

        for group_entity in group:
            # Normalize and split group entity value into words
            group_words = set(
                word.strip(".,;:'\"").lower() for word in group_entity.value.split() if word.strip(".,;:'\"")
            )

            # Check if any words overlap
            if entity_words & group_words:  # Intersection
                return True

        return False

    def _create_tokens_for_entities(self, entities: list[PIIEntity]) -> dict[PIIEntity, RedactionToken]:
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
                value_to_min_index[normalized] = min(value_to_min_index[normalized], token.token_index)

            # Also track individual words for partial matches
            words = normalized.split()
            for word in words:
                word_clean = word.strip(".,;:'\"")
                if word_clean:
                    if word_clean not in value_to_min_index:
                        value_to_min_index[word_clean] = token.token_index
                    else:
                        value_to_min_index[word_clean] = min(value_to_min_index[word_clean], token.token_index)

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
