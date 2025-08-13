"""Batch detection utilities for processing multiple fields efficiently."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from redactyl.detectors.base import PIIDetector
from redactyl.exceptions import BatchDetectionError
from redactyl.protocols import NameParsingDetector
from redactyl.types import PIIEntity

if TYPE_CHECKING:
    from redactyl.callbacks import CallbackContext


@dataclass
class FieldInfo:
    """Information about a field in batch processing."""

    path: str  # Field path (e.g., "user.email")
    value: str  # Field value
    start: int  # Start position in composite text
    end: int  # End position in composite text


class BatchDetector:
    """Handles batch detection of PII across multiple fields.

    Uses position-based tracking instead of separators to avoid conflicts
    with content that might naturally contain separators.
    """

    # Unicode Private Use Area character as field boundary marker
    # This character is reserved and won't appear in normal text
    FIELD_BOUNDARY = "\ue000"

    def __init__(
        self,
        detector: PIIDetector,
        use_position_tracking: bool = True,
        use_name_parsing: bool = True,
        callbacks: "CallbackContext | None" = None,
    ):
        """
        Initialize batch detector.

        Args:
            detector: The underlying PII detector
            use_position_tracking: If True, uses position-based tracking (recommended).
                                  If False, uses boundary markers (legacy mode).
            use_name_parsing: Whether to parse name components
            callbacks: Callback context for event handling
        """
        self.detector = detector
        self.use_position_tracking = use_position_tracking
        self.use_name_parsing = use_name_parsing
        
        if callbacks is None:
            from redactyl.callbacks import CallbackContext
            callbacks = CallbackContext()
        self.callbacks = callbacks

    def detect_batch(self, fields: dict[str, str]) -> dict[str, list[PIIEntity]]:
        """
        Detect PII in multiple fields with a single detector call.

        Uses position-based tracking to safely handle any content without
        separator conflicts.

        Args:
            fields: Mapping of field paths to text values

        Returns:
            Mapping of field paths to detected entities (with adjusted positions)
        """
        if not fields:
            return {}

        # Build composite text and track field positions
        field_infos: list[FieldInfo] = []

        if self.use_position_tracking:
            # Position-based approach: concatenate directly without separators
            composite_text = self._build_composite_position_based(fields, field_infos)
        else:
            # Legacy approach: use boundary markers
            composite_text = self._build_composite_with_boundaries(fields, field_infos)

        # Detect with error handling
        try:
            # Use name parsing if available and requested
            all_entities: list[PIIEntity]
            if self.use_name_parsing and isinstance(self.detector, NameParsingDetector):
                all_entities = self.detector.detect_with_name_parsing(composite_text)
            else:
                all_entities = self.detector.detect(composite_text)
        except Exception as e:
            # For position tracking, no separator issues possible
            # For boundary markers, check if they appear in content
            boundary_issue = False
            if not self.use_position_tracking:
                boundary_issue = any(
                    self.FIELD_BOUNDARY in value for value in fields.values()
                )

            # Trigger callback for batch error
            batch_error = BatchDetectionError(
                "Failed to detect PII in batch",
                failed_fields=list(fields.keys()),
                separator_issue=boundary_issue,
                original_error=e,
            )
            self.callbacks.trigger_batch_error(batch_error)
            raise batch_error from e

        # Map entities back to their fields
        return self._map_entities_to_fields(all_entities, field_infos)

    def _build_composite_position_based(
        self, fields: dict[str, str], field_infos: list[FieldInfo]
    ) -> str:
        """
        Build composite text using position-based tracking.

        This approach uses a pilcrow-based separator (\n¶¶\n) between fields to prevent
        word fusion and ensure name parsers don't treat adjacent fields as
        continuous text. The newlines create paragraph breaks that NLP tools respect,
        while the pilcrows provide a clear, visible boundary that's unlikely to
        appear in natural text.
        
        Raises:
            BatchDetectionError: If any field contains the separator sequence
        """
        FIELD_SEPARATOR = "\n¶¶\n"
        
        # Check if separator exists in any field
        fields_with_separator = [
            path for path, value in fields.items() 
            if FIELD_SEPARATOR in value
        ]
        
        if fields_with_separator:
            from redactyl.exceptions import BatchDetectionError
            raise BatchDetectionError(
                f"Field separator '{repr(FIELD_SEPARATOR)}' found in input fields",
                failed_fields=fields_with_separator,
                separator_issue=True,
                original_error=None,
            )
        
        composite_parts: list[str] = []
        current_pos = 0

        for idx, (path, value) in enumerate(fields.items()):
            # Skip empty fields
            if not value:
                continue

            # Add field separator between fields (not before first)
            # This ensures names at field boundaries aren't merged
            if idx > 0 and composite_parts:
                composite_parts.append(FIELD_SEPARATOR)
                current_pos += len(FIELD_SEPARATOR)

            # Track field info
            field_infos.append(
                FieldInfo(
                    path=path,
                    value=value,
                    start=current_pos,
                    end=current_pos + len(value),
                )
            )

            # Add field value
            composite_parts.append(value)
            current_pos += len(value)

        return "".join(composite_parts)

    def _build_composite_with_boundaries(
        self, fields: dict[str, str], field_infos: list[FieldInfo]
    ) -> str:
        """
        Build composite text using boundary markers (legacy mode).

        Uses Unicode Private Use Area characters that won't appear in normal text.
        """
        composite_parts: list[str] = []
        current_pos = 0

        for idx, (path, value) in enumerate(fields.items()):
            # Skip empty fields
            if not value:
                continue

            # Add boundary marker between fields (not before first)
            if idx > 0 and composite_parts:
                composite_parts.append(self.FIELD_BOUNDARY)
                current_pos += len(self.FIELD_BOUNDARY)

            # Track field info
            field_infos.append(
                FieldInfo(
                    path=path,
                    value=value,
                    start=current_pos,
                    end=current_pos + len(value),
                )
            )

            # Add field value
            composite_parts.append(value)
            current_pos += len(value)

        return "".join(composite_parts)

    def _map_entities_to_fields(
        self, all_entities: list[PIIEntity], field_infos: list[FieldInfo]
    ) -> dict[str, list[PIIEntity]]:
        """
        Map detected entities back to their original fields.

        Handles edge cases like entities spanning field boundaries.
        Preserves original field order for consistent entity numbering.
        """
        # Pre-populate result with field paths in original order
        result: dict[str, list[PIIEntity]] = {
            field_info.path: [] for field_info in field_infos
        }
        unmapped_entities: list[PIIEntity] = []

        for entity in all_entities:
            mapped = False

            # Find which field contains this entity
            for field_info in field_infos:
                # Check if entity is fully within this field's boundaries
                if (
                    field_info.start <= entity.start < field_info.end
                    and field_info.start < entity.end <= field_info.end
                ):
                    # Adjust positions relative to field
                    adjusted_entity = PIIEntity(
                        type=entity.type,
                        value=entity.value,
                        start=entity.start - field_info.start,
                        end=entity.end - field_info.start,
                        confidence=entity.confidence,
                    )

                    # Validate the adjusted positions
                    field_length = len(field_info.value)
                    if adjusted_entity.end > field_length:
                        # Entity extends beyond field - shouldn't happen
                        continue

                    # Add to results (field already exists in result dict)
                    result[field_info.path].append(adjusted_entity)
                    mapped = True
                    break

            if not mapped:
                # Entity spans field boundaries or is outside all fields
                # Can happen if boundary marker gets detected as part of entity
                # We'll skip these as they're likely false positives
                unmapped_entities.append(entity)

        # If we have unmapped entities and we're not using position tracking,
        # it might indicate the boundary marker is being included in detections
        if unmapped_entities and not self.use_position_tracking:
            # Could log a warning here if needed
            pass

        return result

    def detect_batch_with_context(
        self,
        fields: dict[str, str],
        field_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, list[PIIEntity]]:
        """
        Detect PII with field-specific context information.

        This allows passing metadata about fields that might help detection,
        such as expected entity types, confidence thresholds, etc.

        Args:
            fields: Mapping of field paths to text values
            field_contexts: Optional metadata for each field

        Returns:
            Mapping of field paths to detected entities
        """
        # For now, just use basic batch detection
        # Future: Use context to group fields by detection requirements
        return self.detect_batch(fields)


class SmartBatchDetector(BatchDetector):
    """
    Enhanced batch detector with intelligent field grouping.

    Groups fields by their detection requirements for optimal performance.
    Always uses position-based tracking for safety with diverse content.
    """

    def __init__(self, detector: PIIDetector, use_name_parsing: bool = True):
        """
        Initialize smart batch detector.

        Always uses position tracking for maximum reliability.

        Args:
            detector: The underlying PII detector
            use_name_parsing: Whether to parse name components
        """
        # Always use position tracking in smart mode
        super().__init__(
            detector, use_position_tracking=True, use_name_parsing=use_name_parsing
        )

    def detect_batch(
        self,
        fields: dict[str, str],
        field_configs: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, list[PIIEntity]]:
        """
        Detect PII with smart grouping of fields.

        Args:
            fields: Mapping of field paths to text values
            field_configs: Optional configuration for each field

        Returns:
            Mapping of field paths to detected entities
        """
        if not fields:
            return {}

        # Group fields by detection strategy
        groups = self._group_fields(fields, field_configs or {})

        # Process each group
        all_results: dict[str, list[PIIEntity]] = {}

        for _, field_paths in groups.items():
            # Get fields for this group
            group_fields = {path: fields[path] for path in field_paths}

            # Detect PII for this group
            group_results = super().detect_batch(group_fields)

            # Merge results
            all_results.update(group_results)

        return all_results

    def _group_fields(
        self, fields: dict[str, str], field_configs: dict[str, dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Group fields by their detection requirements."""
        groups: dict[str, list[str]] = {"default": []}

        # For now, put all fields in default group
        # Future: Group by confidence threshold, entity types, etc.
        for field_path in fields:
            groups["default"].append(field_path)

        return {k: v for k, v in groups.items() if v}
