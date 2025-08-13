"""Callback management for PII-loop events.

This module provides a centralized way to handle events throughout
the PII detection and redaction process using callbacks instead
of direct logging or printing.
"""

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field

from redactyl.types import PIIEntity, UnredactionIssue


@dataclass
class CallbackContext:
    """Context object containing all event callbacks.
    
    This is passed through the processing pipeline to provide
    consistent event handling without tight coupling to specific
    logging implementations.
    """
    
    on_gliner_unavailable: Callable[[], None] | None = field(default=None)
    on_detection: Callable[[list[PIIEntity]], None] | None = field(default=None)
    on_batch_error: Callable[[Exception], None] | None = field(default=None)
    on_unredaction_issue: Callable[[UnredactionIssue], None] | None = field(default=None)
    on_gliner_model_error: Callable[[str, Exception], None] | None = field(default=None)
    
    @classmethod
    def with_defaults(cls) -> "CallbackContext":
        """Create a context with default warning callbacks."""
        return cls(
            on_gliner_unavailable=lambda: warnings.warn(
                "GLiNER is not installed or unavailable. Install with: pip install redactyl[gliner]. "
                "Falling back to nameparser for name component detection.",
                UserWarning,
                stacklevel=3
            ),
            on_batch_error=lambda exc: warnings.warn(
                f"Batch processing error: {exc}",
                RuntimeWarning,
                stacklevel=3
            ),
            on_gliner_model_error=lambda model, exc: warnings.warn(
                f"Failed to load GLiNER model '{model}': {exc}. "
                "Falling back to nameparser for name component detection.",
                RuntimeWarning,
                stacklevel=3
            ),
        )
    
    @classmethod
    def silent(cls) -> "CallbackContext":
        """Create a context with all callbacks disabled (silent mode)."""
        return cls()
    
    def trigger_gliner_unavailable(self) -> None:
        """Trigger the GLiNER unavailable callback if set."""
        if self.on_gliner_unavailable:
            self.on_gliner_unavailable()
    
    def trigger_detection(self, entities: list[PIIEntity]) -> None:
        """Trigger the detection callback if set."""
        if self.on_detection:
            self.on_detection(entities)
    
    def trigger_batch_error(self, exc: Exception) -> None:
        """Trigger the batch error callback if set."""
        if self.on_batch_error:
            self.on_batch_error(exc)
    
    def trigger_unredaction_issue(self, issue: UnredactionIssue) -> None:
        """Trigger the unredaction issue callback if set."""
        if self.on_unredaction_issue:
            self.on_unredaction_issue(issue)
    
    def trigger_gliner_model_error(self, model_name: str, exc: Exception) -> None:
        """Trigger the GLiNER model error callback if set."""
        if self.on_gliner_model_error:
            self.on_gliner_model_error(model_name, exc)