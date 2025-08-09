import difflib
import re
from typing import Protocol

from redactyl.types import RedactionState, UnredactionIssue


class HallucinationHandler(Protocol):
    def handle(
        self, token: str, state: RedactionState, strict: bool
    ) -> UnredactionIssue | None:
        """
        Handle an unmapped token.

        Args:
            token: The token to handle
            state: The redaction state with valid tokens
            strict: If True, reject fuzzy matches

        Returns:
            UnredactionIssue if token is problematic, None if valid
        """
        ...


class DefaultHallucinationHandler:
    def __init__(self, similarity_threshold: float = 0.8) -> None:
        self._threshold = similarity_threshold

    def handle(
        self, token: str, state: RedactionState, strict: bool
    ) -> UnredactionIssue | None:
        # Check if token exists in state
        if token in state.tokens:
            return None  # Valid token

        # In strict mode, any unmapped token is a hallucination
        if strict:
            return UnredactionIssue(
                token=token,
                issue_type="hallucination",
                replacement=None,
                confidence=0.0,
                details=f"Token {token} not found in state (strict mode)",
            )

        # Try fuzzy matching
        closest_match = self._find_closest_match(token, list(state.tokens.keys()))
        if closest_match:
            similarity = self._calculate_similarity(token, closest_match)

            if similarity >= self._threshold:
                # Good enough match - likely a typo or case variation
                return UnredactionIssue(
                    token=token,
                    issue_type="fuzzy_match",
                    replacement=state.tokens[closest_match].original,
                    confidence=similarity,
                    details=(
                        f"Matched to {closest_match} with {similarity:.2f} confidence"
                    ),
                )

        # No good match found - treat as hallucination
        return UnredactionIssue(
            token=token,
            issue_type="hallucination",
            replacement=None,
            confidence=0.0,
            details=f"Token {token} appears to be LLM-generated",
        )

    def _find_closest_match(self, token: str, candidates: list[str]) -> str | None:
        if not candidates:
            return None

        # First check for case-insensitive exact match
        token_upper = token.upper()
        for candidate in candidates:
            if candidate.upper() == token_upper:
                return candidate

        # Try fuzzy matching, but be careful about different indices
        # Split candidates into those with likely typos vs different tokens
        filtered_candidates: list[str] = []
        for candidate in candidates:
            # Extract the pattern and index
            candidate_match = re.match(r"\[([A-Z_]+)_(\d+)\]", candidate)
            token_match = re.match(r"\[([A-Za-z_]+)_(\d+)\]", token)

            if candidate_match and token_match:
                # cand_prefix = candidate_match.group(1)  # unused
                cand_index = candidate_match.group(2)
                # token_prefix = token_match.group(1).upper()  # unused
                token_index = token_match.group(2)

                # If indices match, it's likely a typo in the prefix
                if cand_index == token_index:
                    filtered_candidates.append(candidate)
                # Don't match tokens with different indices, even if prefix is similar
                # This prevents [EMAIL_2] from matching [EMAIL_1]
            else:
                # Fallback for non-standard tokens
                filtered_candidates.append(candidate)

        if not filtered_candidates:
            return None

        # Use difflib to find close matches
        matches = difflib.get_close_matches(
            token,
            filtered_candidates,
            n=1,
            cutoff=0.7,  # Higher cutoff for safety
        )

        return matches[0] if matches else None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        return difflib.SequenceMatcher(None, str1.upper(), str2.upper()).ratio()
