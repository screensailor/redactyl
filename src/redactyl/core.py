from typing import TYPE_CHECKING

from redactyl.callbacks import CallbackContext
from redactyl.detectors.base import PIIDetector
from redactyl.handlers import DefaultHallucinationHandler, HallucinationHandler
from redactyl.protocols import NameParsingDetector
from redactyl.types import PIIEntity, RedactionState, RedactionToken, UnredactionIssue

if TYPE_CHECKING:
    from redactyl.pydantic_integration import PIIConfig


class PIILoop:
    def __init__(
        self,
        detector: PIIDetector,
        hallucination_handler: HallucinationHandler | None = None,
        use_name_parsing: bool = True,
        callbacks: CallbackContext | None = None,
    ) -> None:
        self._detector = detector
        self._hallucination_handler = (
            hallucination_handler or DefaultHallucinationHandler()
        )
        self._use_name_parsing = use_name_parsing
        self._callbacks = callbacks or CallbackContext.with_defaults()
    
    @classmethod
    def from_config(cls, config: "PIIConfig") -> "PIILoop":
        """Create a PIILoop instance from a PIIConfig.
        
        Args:
            config: PIIConfig with detector and callbacks configured
            
        Returns:
            PIILoop instance configured from the config
        """
        from redactyl.callbacks import CallbackContext
        
        # Create callback context from config
        callbacks = CallbackContext(
            on_gliner_unavailable=config.on_gliner_unavailable,
            on_detection=config.on_detection,
            on_batch_error=config.on_batch_error,
            on_unredaction_issue=config.on_unredaction_issue,
        )
        
        return cls(
            detector=config.detector,
            use_name_parsing=config.use_name_parsing,
            callbacks=callbacks,
        )

    def redact(self, text: str) -> tuple[str, RedactionState]:
        if not text:
            return "", RedactionState()

        # Detect PII entities with optional name parsing
        if self._use_name_parsing and isinstance(self._detector, NameParsingDetector):
            entities = self._detector.detect_with_name_parsing(text)
        else:
            entities = self._detector.detect(text)
        
        # Trigger detection callback if configured
        if entities:
            self._callbacks.trigger_detection(entities)

        # Sort by start position and filter overlapping entities
        entities = self._filter_overlapping_entities(entities)

        # Build redaction state and apply redactions
        state = RedactionState()
        redacted_text = text

        # Group name components and assign indices
        tokens_to_create = self._assign_name_aware_indices(entities)

        # Process entities in reverse order to maintain positions
        for entity, token_index in reversed(tokens_to_create):
            # Create redaction token
            redaction_token = RedactionToken(
                original=entity.value,
                pii_type=entity.type,
                token_index=token_index,
                entity=entity,
            )

            # Add to state
            state = state.with_token(redaction_token.token, redaction_token)

            # Replace in text
            redacted_text = (
                redacted_text[: entity.start]
                + redaction_token.token
                + redacted_text[entity.end :]
            )

        return redacted_text, state

    def unredact(
        self, text: str, state: RedactionState, fuzzy: bool = False
    ) -> tuple[str, list[UnredactionIssue]]:
        """
        Restore original values from redacted text.

        Args:
            text: Text containing redaction tokens
            state: RedactionState with token mappings
            fuzzy: If True, enable fuzzy matching for hallucinated tokens

        Returns:
            Tuple of (unredacted text, list of issues encountered)
        """
        if not text:
            return "", []

        issues: list[UnredactionIssue] = []
        unredacted_text = text

        # Sort tokens by their appearance in text (reverse order for replacement)
        token_positions: list[tuple[int, str]] = []
        for token in state.tokens:
            pos = text.find(token)
            if pos != -1:
                token_positions.append((pos, token))

        # Sort by position (descending) to process from end to start
        token_positions.sort(reverse=True)

        # Replace each token with its original value
        for _, token in token_positions:
            if token in state.tokens:
                original = state.tokens[token].original
                unredacted_text = unredacted_text.replace(token, original)
            else:
                # This shouldn't happen if state is consistent
                issues.append(
                    UnredactionIssue(
                        token=token,
                        issue_type="missing_mapping",
                        replacement=None,
                        confidence=0.0,
                        details=f"Token {token} not found in state",
                    )
                )

        # Check for any remaining tokens that might be hallucinations
        import re

        remaining_tokens = re.findall(r"\[[A-Za-z_]+_\d+\]", unredacted_text)
        for token in remaining_tokens:
            if token not in state.tokens:
                # Use hallucination handler
                # Note: we pass strict=not fuzzy because the handler's strict
                # parameter means "reject fuzzy matches", which is the opposite
                # of our fuzzy parameter
                issue = self._hallucination_handler.handle(
                    token, state, strict=not fuzzy
                )
                if issue:
                    issues.append(issue)
                    # Apply replacement if handler found one (only in fuzzy mode)
                    if issue.replacement and fuzzy:
                        unredacted_text = unredacted_text.replace(
                            token, issue.replacement
                        )

        return unredacted_text, issues

    def _assign_name_aware_indices(
        self, entities: list[PIIEntity]
    ) -> list[tuple[PIIEntity, int]]:
        """
        Assign indices to entities with special handling for name components.

        Name components that came from the same person detection should share
        the same index. Additionally, the same first name appearing later
        should reuse the same person's index (for email context).
        """
        from redactyl.types import PIIType

        # Name-related types that need special handling
        name_types = {
            PIIType.NAME_FIRST,
            PIIType.NAME_MIDDLE,
            PIIType.NAME_LAST,
            PIIType.NAME_TITLE,
        }

        # Track assignments
        tokens_to_create: list[tuple[PIIEntity, int]] = []
        token_counters: dict[str, int] = {}

        # Track people by full name combinations
        # Key: "first_last" or just "first" if no last name
        # Value: person index
        person_registry: dict[str, int] = {}
        # Track people without last names - map first name to person index
        first_name_only_registry: dict[str, int] = {}
        # Track current person index
        person_counter = 0

        # Group consecutive name components
        i = 0
        while i < len(entities):
            entity = entities[i]

            if entity.type in name_types:
                # Collect all consecutive name components
                name_group: list[PIIEntity] = [entity]
                j = i + 1
                while j < len(entities) and entities[j].type in name_types:
                    # Check if positions are close (within reasonable distance)
                    # Use the end of the LAST entity in the group, not j-1
                    last_entity_in_group = name_group[-1]
                    if entities[j].start - last_entity_in_group.end <= 2:
                        # Allow max 2 chars between name components (for spaces)
                        name_group.append(entities[j])
                        j += 1
                    else:
                        break

                # Determine person index for this group
                person_idx = None
                first_name = None
                last_name = None

                # Find first and last names in the group
                for e in name_group:
                    if e.type == PIIType.NAME_FIRST:
                        first_name = e.value.lower()
                    elif e.type == PIIType.NAME_LAST:
                        last_name = e.value.lower()

                # Determine which person this is
                if first_name and last_name:
                    # Full name - check if we've seen this exact combination
                    full_key = f"{first_name}_{last_name}"

                    if full_key in person_registry:
                        # We've seen this exact person before
                        person_idx = person_registry[full_key]
                    elif first_name in first_name_only_registry:
                        # We've seen this first name before (without last name)
                        # Check if the existing person already has a different last name
                        existing_person_idx = first_name_only_registry[first_name]

                        # Check if this person already has a different full name registered
                        person_has_different_last = False
                        for reg_key, reg_idx in person_registry.items():
                            if reg_idx == existing_person_idx and reg_key.startswith(
                                f"{first_name}_"
                            ):
                                # This person already has a full name registered
                                if reg_key != full_key:
                                    # Different last name - this is a different person
                                    person_has_different_last = True
                                    break

                        if person_has_different_last:
                            # Different person with same first name
                            person_counter += 1
                            person_idx = person_counter
                            person_registry[full_key] = person_idx
                        else:
                            # Same person - add this full name to registry
                            person_idx = existing_person_idx
                            person_registry[full_key] = person_idx
                    else:
                        # New person with full name
                        person_counter += 1
                        person_idx = person_counter
                        person_registry[full_key] = person_idx
                        first_name_only_registry[first_name] = person_idx
                elif first_name:
                    # Only have first name - check if we can reuse an existing person
                    if first_name in first_name_only_registry:
                        # Reuse the person who first had this first name
                        person_idx = first_name_only_registry[first_name]
                    else:
                        # New first name we haven't seen
                        person_counter += 1
                        person_idx = person_counter
                        first_name_only_registry[first_name] = person_idx
                elif last_name:
                    # Only have last name (unusual but possible)
                    last_key = f"_{last_name}"
                    if last_key in person_registry:
                        person_idx = person_registry[last_key]
                    else:
                        person_counter += 1
                        person_idx = person_counter
                        person_registry[last_key] = person_idx
                else:
                    # No first or last name (e.g., just title or middle name)
                    person_counter += 1
                    person_idx = person_counter

                # Assign the same index to all components in this group
                for e in name_group:
                    tokens_to_create.append((e, person_idx))

                # Move past this group
                i = j
            else:
                # Non-name entity, use regular counter
                entity_type_name = entity.type.name
                if entity_type_name not in token_counters:
                    token_counters[entity_type_name] = 0
                token_counters[entity_type_name] += 1
                tokens_to_create.append((entity, token_counters[entity_type_name]))
                i += 1

        return tokens_to_create

    def _filter_overlapping_entities(
        self, entities: list[PIIEntity]
    ) -> list[PIIEntity]:
        if not entities:
            return []

        # Sort by start position, then by length (descending), then by confidence (descending)
        # This prefers longer, more specific entities over shorter ones
        sorted_entities = sorted(
            entities, key=lambda e: (e.start, -(e.end - e.start), -e.confidence)
        )

        filtered: list[PIIEntity] = []
        last_end = -1

        for entity in sorted_entities:
            # Skip if this entity overlaps with a previously selected one
            if entity.start >= last_end:
                filtered.append(entity)
                last_end = entity.end

        return filtered
