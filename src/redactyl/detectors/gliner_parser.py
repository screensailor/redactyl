"""GLiNER-based name component parser.

This module provides optional GLiNER support for enhanced name parsing.
GLiNER must be installed separately: pip install redactyl[gliner]

We intentionally import the GLiNER symbol at module load with a fallback
to `None` so tests and downstream code can patch or inspect availability via
`redactyl.detectors.gliner_parser.GLiNER` without importing the optional
dependency.
"""

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redactyl.callbacks import CallbackContext

import sys

from redactyl.types import PIIEntity, PIIType

# Optional import: expose a module-level GLiNER symbol for patching/tests
try:  # pragma: no cover - exercised via unit tests
    from gliner import GLiNER  # type: ignore[import-untyped]
except Exception:  # ImportError or any failure
    GLiNER = None  # type: ignore[assignment]

# Global cache for loaded GLiNER models to avoid repeated downloads
_GLINER_MODEL_CACHE: dict[str, Any] = {}


def _clear_gliner_cache() -> None:
    """Clear the GLiNER model cache. Used for testing."""
    global _GLINER_MODEL_CACHE
    _GLINER_MODEL_CACHE.clear()


def _gliner_unavailable() -> bool:
    """Return True if GLiNER appears unavailable in the current runtime.

    Considers both the module-level import fallback and runtime patches to
    sys.modules used by tests to simulate the library not being present.
    """
    mod = sys.modules.get("gliner")
    return GLiNER is None or mod is None


@dataclass
class GlinerNameParser:
    """Parse names into components using GLiNER model.
    
    GLiNER is an optional dependency. If not installed, this parser
    will gracefully return None and allow fallback to nameparser.
    
    Installation: pip install redactyl[gliner]
    """

    model_name: str = "urchade/gliner_multi_pii-v1"
    callbacks: "CallbackContext | None" = None
    _model: Any = None  # GLiNER instance
    _initialized: bool = False
    _available: bool = False  # Track if GLiNER is available

    def __post_init__(self) -> None:
        """Initialize the model lazily.

        If GLiNER is not available at import time, register that state and
        emit a warning via callbacks (unless silenced).
        """
        self._model = None
        self._initialized = False
        self._available = False
        if self.callbacks is None:
            from redactyl.callbacks import CallbackContext
            self.callbacks = CallbackContext.with_defaults()

        # If GLiNER is clearly unavailable, provide early signal
        if _gliner_unavailable():
            # Let callbacks handle whether to warn or stay silent
            try:
                self.callbacks.trigger_gliner_unavailable()
            except Exception:
                # Never let callbacks break initialization
                warnings.warn(
                    "GLiNER is not installed or unavailable. Install with: "
                    "pip install redactyl[gliner]. Falling back to nameparser.",
                    UserWarning,
                    stacklevel=3,
                )
            # Mark initialized to avoid repeated import attempts
            self._initialized = True
            self._available = False

    def _ensure_initialized(self) -> None:
        """Lazy initialize the GLiNER model with caching."""
        if not self._initialized:
            try:
                if _gliner_unavailable():
                    raise ImportError("gliner not available")
                
                # Check cache first to avoid repeated downloads
                # But only use cache if GLiNER is still available (for test mocking)
                if self.model_name in _GLINER_MODEL_CACHE and not _gliner_unavailable():
                    self._model = _GLINER_MODEL_CACHE[self.model_name]
                else:
                    # Load model and cache it
                    self._model = GLiNER.from_pretrained(self.model_name)  # type: ignore[union-attr]
                    _GLINER_MODEL_CACHE[self.model_name] = self._model
                
                self._initialized = True
                self._available = True
            except ImportError:
                # GLiNER is not installed - this is expected for optional dependency
                if self.callbacks is not None:
                    self.callbacks.trigger_gliner_unavailable()
                self._initialized = True
                self._available = False
            except Exception as e:
                # GLiNER is installed but failed to load model
                if self.callbacks is not None:
                    self.callbacks.trigger_gliner_model_error(self.model_name, e)
                self._initialized = True
                self._available = False

    @property
    def is_available(self) -> bool:
        """Check if GLiNER is available and loaded."""
        if not self._initialized:
            self._ensure_initialized()
        return self._available

    def parse_name_components(self, person_entity: PIIEntity) -> list[PIIEntity] | None:
        """
        Parse a PERSON entity into name components using GLiNER.

        Args:
            person_entity: The PERSON entity to parse

        Returns:
            List of component entities or None if parsing fails or GLiNER is unavailable
        """
        self._ensure_initialized()

        if self._model is None:
            # Model failed to load, return None to fallback
            # Emit availability warning here as well to ensure callers
            # get a signal even if initialization warnings were missed.
            if self.callbacks is not None:
                self.callbacks.trigger_gliner_unavailable()
            return None

        # Define the labels we want to extract
        labels = ["title", "first_name", "middle_name", "last_name"]

        try:
            # Get predictions from GLiNER
            predictions: list[dict[str, Any]] = self._model.predict_entities(
                person_entity.value, labels, threshold=0.5
            )

            if not predictions:
                return None

            components: list[PIIEntity] = []

            # Map GLiNER labels to our PIIType enum
            label_to_type = {
                "title": PIIType.NAME_TITLE,
                "first_name": PIIType.NAME_FIRST,
                "middle_name": PIIType.NAME_MIDDLE,
                "last_name": PIIType.NAME_LAST,
            }

            # Convert GLiNER predictions to PIIEntity objects
            for pred in predictions:
                label: str = pred.get("label", "")
                if label not in label_to_type:
                    continue

                text: str = pred.get("text", "")
                if not text:
                    continue

                # Find the position of this component in the original entity value
                start_in_value = person_entity.value.find(text)
                if start_in_value == -1:
                    continue

                # Calculate absolute positions
                start = person_entity.start + start_in_value
                end = start + len(text)

                components.append(
                    PIIEntity(
                        type=label_to_type[label],
                        value=text,
                        start=start,
                        end=end,
                        confidence=float(pred.get("score", person_entity.confidence)),
                    )
                )

            # Special case: single name detected as last name should be first name
            # (common GLiNER behavior for single names)
            if len(components) == 1 and components[0].type == PIIType.NAME_LAST:
                # Check if it's a single word (no spaces)
                if " " not in person_entity.value.strip():
                    components[0] = PIIEntity(
                        type=PIIType.NAME_FIRST,
                        value=components[0].value,
                        start=components[0].start,
                        end=components[0].end,
                        confidence=components[0].confidence,
                    )

            # Check if we missed a title at the beginning
            # Common titles that GLiNER might miss
            titles = [
                "Dr.",
                "Mr.",
                "Ms.",
                "Mrs.",
                "Prof.",
                "Dr",
                "Mr",
                "Ms",
                "Mrs",
                "Prof",
            ]
            name_lower = person_entity.value.lower()
            for title in titles:
                if name_lower.startswith(title.lower()):
                    # Check if we already have a title component
                    has_title = any(c.type == PIIType.NAME_TITLE for c in components)
                    if not has_title:
                        # Add the title component
                        title_end = len(title)
                        if (
                            title_end < len(person_entity.value)
                            and person_entity.value[title_end] == "."
                        ):
                            title_end += 1
                        components.insert(
                            0,
                            PIIEntity(
                                type=PIIType.NAME_TITLE,
                                value=person_entity.value[:title_end],
                                start=person_entity.start,
                                end=person_entity.start + title_end,
                                confidence=0.9,
                            ),
                        )
                    break

            # Sort components by position
            components.sort(key=lambda e: e.start)

            return components if components else None

        except Exception:
            # If GLiNER fails, return None to fallback
            return None

    def parse_single_name(self, name: str) -> dict[str, str]:
        """
        Parse a standalone name string into components.

        Useful for testing and direct name parsing. Returns empty values
        if GLiNER is not available.

        Args:
            name: The name string to parse

        Returns:
            Dictionary with keys 'title', 'first', 'middle', 'last'.
            All values will be empty strings if GLiNER is unavailable.
        """
        self._ensure_initialized()

        result = {"title": "", "first": "", "middle": "", "last": ""}

        if self._model is None:
            return result

        labels = ["title", "first_name", "middle_name", "last_name"]

        try:
            predictions: list[dict[str, Any]] = self._model.predict_entities(
                name, labels, threshold=0.5
            )

            for pred in predictions:
                label: str = pred.get("label", "")
                text: str = pred.get("text", "")

                if label == "title":
                    result["title"] = text
                elif label == "first_name":
                    result["first"] = text
                elif label == "middle_name":
                    result["middle"] = text
                elif label == "last_name":
                    result["last"] = text

        except Exception:
            pass

        return result
