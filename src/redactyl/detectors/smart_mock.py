"""Smart mock detector for testing batch operations."""

from redactyl.detectors.base import BaseDetector
from redactyl.types import PIIEntity, PIIType


class SmartMockDetector(BaseDetector):
    """
    Smart mock detector that can find entities in actual text positions.

    This is useful for testing batch detection where positions matter.
    """

    def __init__(self, entity_specs: list[tuple[str, PIIType]] | None = None):
        """
        Initialize with entity specifications.

        Args:
            entity_specs: List of (value, type) tuples to detect
        """
        self.entity_specs = entity_specs or []

    def detect(self, text: str) -> list[PIIEntity]:
        """
        Detect entities based on specifications, finding actual positions in text.
        """
        entities: list[PIIEntity] = []

        for value, pii_type in self.entity_specs:
            # Find all occurrences of this value in the text
            start = 0
            while True:
                pos = text.find(value, start)
                if pos == -1:
                    break

                entities.append(
                    PIIEntity(
                        type=pii_type,
                        value=value,
                        start=pos,
                        end=pos + len(value),
                        confidence=0.95,
                    )
                )

                start = pos + len(value)

        # Filter overlapping entities - keep longer ones with higher priority
        return self._filter_overlapping(entities)

    def _filter_overlapping(self, entities: list[PIIEntity]) -> list[PIIEntity]:
        """Filter overlapping entities, keeping the longer/more specific ones.
        
        Policy: Prefer longer spans (more specific) over shorter ones.
        This is consistent with core.py's _filter_overlapping_entities.
        """
        if not entities:
            return []

        # Sort by start position, then by length (descending), then by confidence (descending)
        # This matches core.py's _filter_overlapping_entities for consistency
        sorted_entities = sorted(entities, key=lambda e: (e.start, -(e.end - e.start), -e.confidence))

        filtered: list[PIIEntity] = []
        last_end = -1

        for entity in sorted_entities:
            # Skip if this entity overlaps with a previously selected one
            if entity.start >= last_end:
                filtered.append(entity)
                last_end = entity.end
            elif entity.end > last_end:
                # This entity extends beyond the previous one
                # Check if we should replace the previous one
                if filtered and entity.start < filtered[-1].end:
                    # They overlap - keep the longer one
                    if (entity.end - entity.start) > (
                        filtered[-1].end - filtered[-1].start
                    ):
                        # This one is longer, replace
                        filtered[-1] = entity
                        last_end = entity.end

        return filtered

    def detect_with_name_parsing(self, text: str) -> list[PIIEntity]:
        """
        Detect with name component parsing.

        For testing, we'll parse simple names like "Dr. John Smith" into components.
        """
        entities: list[PIIEntity] = []

        # First do regular detection
        base_entities = self.detect(text)

        # Then parse any PERSON entities into components
        for entity in base_entities:
            if entity.type == PIIType.PERSON:
                # Simple parsing for testing
                name_text = entity.value
                parts = name_text.split()

                current_pos = entity.start
                # Track if we've seen the first name yet (excluding titles)
                seen_first_name = False
                
                for i, part in enumerate(parts):
                    # Determine type based on position and content
                    if part in ["Dr.", "Mr.", "Ms.", "Mrs."]:
                        component_type = PIIType.NAME_TITLE
                    elif i == len(parts) - 1:
                        # Last part is always last name
                        component_type = PIIType.NAME_LAST
                    elif not seen_first_name:
                        # First non-title part is first name
                        component_type = PIIType.NAME_FIRST
                        seen_first_name = True
                    else:
                        # Everything between first and last is middle
                        component_type = PIIType.NAME_MIDDLE

                    # Find exact position of this part
                    part_pos = text.find(part, current_pos)
                    if part_pos != -1:
                        entities.append(
                            PIIEntity(
                                type=component_type,
                                value=part,
                                start=part_pos,
                                end=part_pos + len(part),
                                confidence=0.90,
                            )
                        )
                        current_pos = part_pos + len(part)
            else:
                # Keep non-person entities as-is
                entities.append(entity)

        return entities
