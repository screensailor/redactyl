"""Redactyl: Fast, deterministic PII redaction using type-preserving tokens with perfect reversibility."""

__version__ = "0.1.1"

from redactyl.callbacks import CallbackContext
from redactyl.core import PIILoop
from redactyl.detectors import MockDetector, PIIDetector
from redactyl.handlers import DefaultHallucinationHandler, HallucinationHandler
from redactyl.pydantic_integration import (
    HallucinationResponse,
    PIIConfig,
    pii_field,
)
from redactyl.session import PIISession
from redactyl.types import (
    PIIEntity,
    PIIType,
    RedactionState,
    RedactionToken,
    UnredactionIssue,
)

__all__ = [
    "PIILoop",
    "PIISession",
    "PIIDetector",
    "MockDetector",
    "HallucinationHandler",
    "DefaultHallucinationHandler",
    "HallucinationResponse",
    "PIIEntity",
    "PIIType",
    "RedactionState",
    "RedactionToken",
    "UnredactionIssue",
    "PIIConfig",
    "pii_field",
    "CallbackContext",
]
