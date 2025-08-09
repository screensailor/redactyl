from redactyl.core import PIILoop
from redactyl.types import RedactionState, RedactionToken, UnredactionIssue


class PIISession:
    def __init__(
        self, loop: PIILoop, initial_state: RedactionState | None = None
    ) -> None:
        self._loop = loop
        self._accumulated_state = initial_state or RedactionState()
        self._token_counters: dict[str, int] = {}

        # Initialize counters from initial state
        if initial_state:
            for token in initial_state.tokens.values():
                entity_type = token.pii_type.name
                current_max = self._token_counters.get(entity_type, 0)
                self._token_counters[entity_type] = max(current_max, token.token_index)

    def __enter__(self) -> "PIISession":
        return self

    def __exit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object | None
    ) -> None:
        # Could add cleanup or persistence here if needed
        pass

    def redact(self, text: str) -> str:
        if not text:
            return ""

        # Get base redaction from loop
        redacted_temp, new_state = self._loop.redact(text)

        # We need to renumber tokens based on accumulated counters
        # First, build mapping of old tokens to new tokens
        token_mapping: dict[str, str] = {}
        updated_tokens: dict[str, RedactionToken] = {}

        # Sort tokens by their position in text to maintain order
        sorted_tokens = sorted(
            new_state.tokens.items(), key=lambda x: x[1].entity.start
        )

        for old_token, redaction_token in sorted_tokens:
            entity_type = redaction_token.pii_type.name

            # Get next index for this type
            if entity_type not in self._token_counters:
                self._token_counters[entity_type] = 0
            self._token_counters[entity_type] += 1
            new_index = self._token_counters[entity_type]

            # Create new token with updated index
            new_token_str = f"[{entity_type}_{new_index}]"
            token_mapping[old_token] = new_token_str

            # Create updated RedactionToken
            updated_token = RedactionToken(
                original=redaction_token.original,
                pii_type=redaction_token.pii_type,
                token_index=new_index,
                entity=redaction_token.entity,
            )
            updated_tokens[new_token_str] = updated_token

        # Apply token mapping to redacted text
        # Sort tokens by length in descending order to avoid partial replacements
        # (e.g., replace "[PERSON_11]" before "[PERSON_1]")
        redacted = redacted_temp
        sorted_mappings = sorted(token_mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for old_token, new_token in sorted_mappings:
            redacted = redacted.replace(old_token, new_token)

        # Create new state with updated tokens
        new_accumulated_state = RedactionState(
            tokens=updated_tokens,
            metadata=new_state.metadata,
            created_at=new_state.created_at,
        )

        # Merge with accumulated state
        self._accumulated_state = self._accumulated_state.merge(new_accumulated_state)

        return redacted

    def unredact(
        self, text: str, fuzzy: bool = False
    ) -> tuple[str, list[UnredactionIssue]]:
        return self._loop.unredact(text, self._accumulated_state, fuzzy=fuzzy)

    def get_state(self) -> RedactionState:
        return self._accumulated_state
