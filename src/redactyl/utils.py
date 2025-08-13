"""Utility functions for redactyl."""

from redactyl.types import PIIEntity, RedactionToken


def filter_overlapping_entities(entities: list[PIIEntity]) -> list[PIIEntity]:
    """Filter overlapping entities, preferring longer and higher confidence ones."""
    if not entities:
        return []
    sorted_entities = sorted(entities, key=lambda e: (e.start, -(e.end - e.start), -e.confidence))
    filtered: list[PIIEntity] = []
    last_end = -1
    for e in sorted_entities:
        if e.start >= last_end:
            filtered.append(e)
            last_end = e.end
    return filtered


def filter_overlapping_tokens(tokens: list[RedactionToken]) -> list[RedactionToken]:
    """Filter overlapping tokens, preferring longer and higher confidence ones."""
    if not tokens:
        return []
    sorted_tokens = sorted(
        tokens,
        key=lambda t: (
            t.entity.start,
            -(t.entity.end - t.entity.start),
            -t.entity.confidence,
        ),
    )
    filtered: list[RedactionToken] = []
    last_end = -1
    for t in sorted_tokens:
        if t.entity.start >= last_end:
            filtered.append(t)
            last_end = t.entity.end
    return filtered
