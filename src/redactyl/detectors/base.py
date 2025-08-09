"""Base detector interfaces."""

from abc import ABC, abstractmethod
from typing import Protocol

from redactyl.types import PIIEntity


class PIIDetector(Protocol):
    """Protocol for PII detectors."""

    def detect(self, text: str) -> list[PIIEntity]: ...


class BaseDetector(ABC):
    """Abstract base class for PII detectors."""

    @abstractmethod
    def detect(self, text: str) -> list[PIIEntity]:
        """Detect PII entities in the given text."""
        pass
