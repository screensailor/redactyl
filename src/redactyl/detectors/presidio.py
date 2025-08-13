"""Presidio-based PII detector implementation."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from redactyl.detectors import BaseDetector
from redactyl.types import PIIEntity, PIIType

if TYPE_CHECKING:
    from redactyl.callbacks import CallbackContext
    from redactyl.detectors.gliner_parser import GlinerNameParser

# Mapping from Presidio entity types to our PIIType enum
PRESIDIO_TO_PII_TYPE: dict[str, PIIType] = {
    "PERSON": PIIType.PERSON,
    "EMAIL_ADDRESS": PIIType.EMAIL,
    "PHONE_NUMBER": PIIType.PHONE,
    "LOCATION": PIIType.LOCATION,
    "CREDIT_CARD": PIIType.CREDIT_CARD,
    "US_SSN": PIIType.SSN,
    "US_ITIN": PIIType.SSN,  # treat ITIN as sensitive like SSN
    "IP_ADDRESS": PIIType.IP_ADDRESS,
    "URL": PIIType.URL,
    "DATE_TIME": PIIType.DATE,
    "ORGANIZATION": PIIType.ORGANIZATION,
    # Name components (we'll handle these specially)
    "TITLE": PIIType.NAME_TITLE,
    "FIRST_NAME": PIIType.NAME_FIRST,
    "MIDDLE_NAME": PIIType.NAME_MIDDLE,
    "LAST_NAME": PIIType.NAME_LAST,
}


@dataclass
class PresidioDetector(BaseDetector):
    """PII detector using Microsoft Presidio.
    
    Supports optional GLiNER integration for enhanced name parsing.
    Install GLiNER with: pip install redactyl[gliner]
    """

    confidence_threshold: float = 0.7
    supported_entities: list[str] | None = None
    language: str = "en"
    use_gliner_for_names: bool = True
    callbacks: "CallbackContext | None" = None
    _gliner_parser: "GlinerNameParser | None" = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize the Presidio analyzer engine."""
        # Configure NLP engine provider
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }

        # Create NLP engine
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()

        # Initialize analyzer with NLP engine
        self._analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, supported_languages=[self.language]
        )

        # If no entities specified, use all mapped ones
        if self.supported_entities is None:
            self.supported_entities = list(PRESIDIO_TO_PII_TYPE.keys())

        # Initialize callbacks if not provided
        if self.callbacks is None:
            from redactyl.callbacks import CallbackContext
            self.callbacks = CallbackContext.with_defaults()

        # Initialize GLiNER parser if requested
        if self.use_gliner_for_names:
            try:
                from redactyl.detectors.gliner_parser import GlinerNameParser
                
                self._gliner_parser = GlinerNameParser(callbacks=self.callbacks)
                # Check if GLiNER is actually available
                if not self._gliner_parser.is_available:
                    self.callbacks.trigger_gliner_unavailable()
            except ImportError:
                self.callbacks.trigger_gliner_unavailable()
                self._gliner_parser = None

    def detect(self, text: str) -> list[PIIEntity]:
        """Detect PII entities in text using Presidio."""
        if not text:
            return []

        # Run Presidio analysis
        # Use a low threshold at the analyzer level and filter per-entity
        # to allow nuanced defaults (e.g., URLs can be slightly lower).
        results = self._analyzer.analyze(
            text=text,
            language=self.language,
            entities=self.supported_entities,
            score_threshold=0.0,
        )

        # Convert Presidio results to our PIIEntity format
        entities: list[PIIEntity] = []
        for result in results:
            # Skip if we don't have a mapping for this entity type
            if result.entity_type not in PRESIDIO_TO_PII_TYPE:
                continue
            # Apply per-entity thresholding
            entity_type = result.entity_type
            score = float(result.score)
            # Default effective threshold
            effective_threshold = float(self.confidence_threshold)
            # URLs often score a bit lower; accept with a slightly lower default
            if entity_type == "URL":
                effective_threshold = min(effective_threshold, 0.5)
            if score < effective_threshold:
                continue
            pii_type = PRESIDIO_TO_PII_TYPE[result.entity_type]
            value = text[result.start : result.end]

            entity = PIIEntity(
                type=pii_type,
                value=value,
                start=result.start,
                end=result.end,
                confidence=result.score,
            )
            entities.append(entity)

        # Fallback: add simple pattern-based detections for common cases
        # that Presidio may score low or miss entirely with minimal context.
        try:
            import re

            # Combine adjacent capitalized words into a PERSON when only the first
            # name was detected (e.g., "Jane" + "Doe" → "Jane Doe").
            enriched: list[PIIEntity] = []
            for e in entities:
                if e.type == PIIType.PERSON and " " not in e.value:
                    # Look for a following capitalized word immediately after
                    m = re.match(r"\s+([A-Z][a-z]+)\b", text[e.end : e.end + 32])
                    if m:
                        # Found last name after first name
                        start = e.start
                        end = e.end + m.end(1)
                        full = text[start:end]
                        # Require simple First Last pattern
                        if re.fullmatch(r"[A-Z][a-z]+\s+[A-Z][a-z]+", full):
                            enriched.append(
                                PIIEntity(
                                    type=PIIType.PERSON,
                                    value=full,
                                    start=start,
                                    end=end,
                                    confidence=e.confidence,
                                )
                            )
            entities.extend(enriched)

            # 7-digit local phone numbers (e.g., 555-1234)
            phone_pattern = re.compile(r"(?<!\d)(\d{3}[\-\.\s]\d{4})(?!\d)")
            # International/NANP style with country code (e.g., +1-555-0123)
            intl_phone_pattern = re.compile(r"(?<!\d)(\+\d{1,3}[\-\.\s]?\d{3}[\-\.\s]\d{4})(?!\d)")
            # US SSN/ITIN patterns (e.g., 987-65-4321)
            ssn_pattern = re.compile(r"(?<!\d)(\d{3}-\d{2}-\d{4})(?!\d)")
            existing_spans = {(e.start, e.end) for e in entities}
            for m in phone_pattern.finditer(text):
                start, end = m.start(1), m.end(1)
                if (start, end) in existing_spans:
                    continue
                entities.append(
                    PIIEntity(
                        type=PIIType.PHONE,
                        value=text[start:end],
                        start=start,
                        end=end,
                        confidence=0.8,
                    )
                )
            for m in intl_phone_pattern.finditer(text):
                start, end = m.start(1), m.end(1)
                if (start, end) in existing_spans:
                    continue
                entities.append(
                    PIIEntity(
                        type=PIIType.PHONE,
                        value=text[start:end],
                        start=start,
                        end=end,
                        confidence=0.85,
                    )
                )

            # Only add SSN if it's in supported entities
            if "US_SSN" in self.supported_entities or "US_ITIN" in self.supported_entities:
                for m in ssn_pattern.finditer(text):
                    start, end = m.start(1), m.end(1)
                    if (start, end) in existing_spans:
                        continue
                    entities.append(
                        PIIEntity(
                            type=PIIType.SSN,
                            value=text[start:end],
                            start=start,
                            end=end,
                            confidence=0.9,
                        )
                    )
        except Exception:
            pass

        return entities

    def detect_with_name_parsing(self, text: str) -> list[PIIEntity]:
        """
        Detect PII with enhanced name component detection.

        This method first detects PERSON entities, then attempts to
        parse them into components (title, first, middle, last).
        
        Uses GLiNER if available and requested, otherwise falls back to nameparser.
        """
        # Get base detections
        entities = self.detect(text)

        # Process PERSON entities to extract components
        enhanced_entities: list[PIIEntity] = []
        for entity in entities:
            if entity.type == PIIType.PERSON:
                # Try to parse name components
                components = self._parse_name_components(entity)
                if components:
                    enhanced_entities.extend(components)
                else:
                    # Keep original if parsing fails
                    enhanced_entities.append(entity)
            else:
                enhanced_entities.append(entity)

        return enhanced_entities

    def _parse_name_components(
        self, person_entity: PIIEntity
    ) -> list[PIIEntity] | None:
        """Parse a PERSON entity into name components.
        
        Attempts to use GLiNER first if available, then falls back to nameparser.
        """
        # First try GLiNER if available and actually loaded
        if self._gliner_parser is not None and self._gliner_parser.is_available:
            gliner_components = self._gliner_parser.parse_name_components(person_entity)
            if gliner_components:
                return gliner_components

        # Fallback to nameparser if GLiNER fails or is not available
        try:
            from nameparser import HumanName  # type: ignore[import-untyped]

            name = HumanName(person_entity.value)
            components: list[PIIEntity] = []

            # Track position within the original entity
            original_text = person_entity.value

            # Helper to find component position in original text
            def add_component(component_value: str, component_type: PIIType) -> None:
                if not component_value:
                    return

                # Find position of component in original text
                idx = original_text.find(component_value)
                if idx != -1:
                    components.append(
                        PIIEntity(
                            type=component_type,
                            value=component_value,
                            start=person_entity.start + idx,
                            end=person_entity.start + idx + len(component_value),
                            confidence=person_entity.confidence,
                        )
                    )

            # Add components in typical order
            if name.title:
                add_component(name.title, PIIType.NAME_TITLE)
            if name.first:
                add_component(name.first, PIIType.NAME_FIRST)
            if name.middle:
                add_component(name.middle, PIIType.NAME_MIDDLE)
            if name.last:
                add_component(name.last, PIIType.NAME_LAST)

            return components if components else None

        except Exception:
            # If parsing fails, return None to keep original entity
            return None
