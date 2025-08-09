"""Mock detector for testing."""

from redactyl.detectors.base import BaseDetector
from redactyl.types import PIIEntity


class MockDetector(BaseDetector):
    """Mock detector that returns predefined entities."""

    def __init__(self, entities: list[PIIEntity]) -> None:
        self._entities = entities

    def detect(self, text: str) -> list[PIIEntity]:
        """Return the predefined entities."""
        return self._entities
