"""Custom exceptions for redactyl with helpful error messages."""

from typing import Any


class PIILoopError(Exception):
    """Base exception for all redactyl errors."""

    pass


class DetectorError(PIILoopError):
    """Error in PII detection."""

    pass


class BatchDetectionError(DetectorError):
    """Error during batch detection with helpful context."""

    def __init__(
        self,
        message: str,
        failed_fields: list[str] | None = None,
        separator_issue: bool = False,
        original_error: Exception | None = None,
    ):
        self.failed_fields = failed_fields or []
        self.separator_issue = separator_issue
        self.original_error = original_error

        # Build detailed error message
        details = [message]

        if failed_fields:
            details.append(f"Failed fields: {', '.join(failed_fields)}")

        if separator_issue:
            details.append(
                "The field boundary marker appears in your content. "
                "Enable position-based tracking with use_position_tracking=True "
                "or use a different boundary character."
            )

        if original_error:
            details.append(f"Original error: {str(original_error)}")

        super().__init__("\n".join(details))


class TokenizationError(PIILoopError):
    """Error in token assignment or tracking."""

    def __init__(
        self,
        message: str,
        entity: Any | None = None,
        conflicting_tokens: list[str] | None = None,
    ):
        self.entity = entity
        self.conflicting_tokens = conflicting_tokens

        details = [message]

        if entity:
            details.append(f"Entity: {entity}")

        if conflicting_tokens:
            details.append(f"Conflicting tokens: {conflicting_tokens}")

        super().__init__("\n".join(details))


class UnredactionError(PIILoopError):
    """Error during unredaction process."""

    def __init__(
        self,
        message: str,
        unmapped_tokens: list[str] | None = None,
        fuzzy_enabled: bool = False,
    ):
        self.unmapped_tokens = unmapped_tokens or []
        self.fuzzy_enabled = fuzzy_enabled

        details = [message]

        if unmapped_tokens:
            details.append(f"Unmapped tokens: {unmapped_tokens}")

            if not fuzzy_enabled:
                details.append(
                    "Tip: Enable fuzzy matching with fuzzy=True to handle "
                    "LLM-generated token variations."
                )

        super().__init__("\n".join(details))


class ConfigurationError(PIILoopError):
    """Error in configuration or setup."""

    def __init__(
        self,
        message: str,
        missing_dependency: str | None = None,
        config_key: str | None = None,
    ):
        self.missing_dependency = missing_dependency
        self.config_key = config_key

        details = [message]

        if missing_dependency:
            details.append(
                f"Missing dependency: {missing_dependency}. "
                f"Install with: pip install {missing_dependency}"
            )

        if config_key:
            details.append(f"Configuration key: {config_key}")

        super().__init__("\n".join(details))


class NameParsingError(PIILoopError):
    """Error parsing name components."""

    def __init__(
        self,
        message: str,
        name_value: str | None = None,
        parse_result: Any | None = None,
    ):
        self.name_value = name_value
        self.parse_result = parse_result

        details = [message]

        if name_value:
            details.append(f"Name value: '{name_value}'")

        if parse_result:
            details.append(f"Parse result: {parse_result}")

        details.append(
            "Note: Name parsing may fail for non-Western names, "
            "single names, or names with unusual formatting."
        )

        super().__init__("\n".join(details))
