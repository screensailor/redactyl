"""Common protocols used across pii-loop."""

from typing import Protocol, runtime_checkable

from redactyl.types import PIIEntity


@runtime_checkable
class NameParsingDetector(Protocol):
    """Protocol for detectors that support name parsing."""

    def detect_with_name_parsing(self, text: str) -> list[PIIEntity]: ...